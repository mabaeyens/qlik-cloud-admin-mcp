import asyncio
import json
import os
import sys
from typing import Optional

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

load_dotenv()

mcp = FastMCP("qlik-cloud-admin")

QLIK_API_KEY = os.getenv("QLIK_API_KEY", "")
RECYCLE_BIN_NAME = "Recycle Bin"


def _build_env() -> dict:
    """Return environment for qlik subprocess, injecting API key if set."""
    env = os.environ.copy()
    if QLIK_API_KEY:
        env["QLIK_API_KEY"] = QLIK_API_KEY
    return env


async def _run_qlik(args: list[str]) -> str:
    """Run a qlik raw subcommand and return stdout or a formatted error."""
    cmd = ["qlik"] + args
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=_build_env(),
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30.0)
    except FileNotFoundError:
        return "Error: 'qlik' binary not found. Make sure qlik-cli is installed and on PATH."
    except asyncio.TimeoutError:
        return "Error: qlik command timed out after 30 seconds."
    except Exception as e:
        return f"Error: unexpected exception: {e}"

    out = stdout.decode().strip()
    err = stderr.decode().strip()

    if proc.returncode != 0:
        return f"Error (exit {proc.returncode}): {err or out}"

    return out or "(empty response)"


# ---------------------------------------------------------------------------
# Recycle bin helpers
# ---------------------------------------------------------------------------

async def _resolve_name(resource_id: str, resource_type: str) -> str:
    """Try to resolve a human-readable name for a resource via the items API.
    Falls back to the resource ID if resolution fails."""
    raw = await _run_qlik([
        "raw", "get", "v1/items",
        "--query", f"resourceId={resource_id}",
        "--query", f"resourceType={resource_type}",
    ])
    if raw.startswith("Error"):
        return resource_id
    try:
        parsed = json.loads(raw)
        items = parsed if isinstance(parsed, list) else parsed.get("data", [])
        return items[0].get("name", resource_id) if items else resource_id
    except (json.JSONDecodeError, AttributeError, IndexError):
        return resource_id


async def _find_recycle_bin() -> tuple[str, None] | tuple[None, str]:
    """Return (space_id, None) if the Recycle Bin space exists, or (None, error_message)."""
    raw = await _run_qlik(["raw", "get", "v1/spaces", "--query", f"name={RECYCLE_BIN_NAME}"])
    if raw.startswith("Error"):
        return None, raw
    try:
        parsed = json.loads(raw)
        spaces = parsed if isinstance(parsed, list) else parsed.get("data", [])
        matches = [s for s in spaces if s.get("name") == RECYCLE_BIN_NAME]
        if not matches:
            return None, (
                f"Recycle bin unavailable: no shared space named '{RECYCLE_BIN_NAME}' "
                "exists in this tenant. That space must be created by an admin before "
                "resources can be retired."
            )
        return matches[0]["id"], None
    except (json.JSONDecodeError, AttributeError):
        return None, f"Error: could not parse spaces response: {raw}"


async def _move_to_recycle_bin(resource_type: str, resource_id: str, space_id: str) -> str:
    """Move a resource to the Recycle Bin space using the appropriate API endpoint."""
    if resource_type == "app":
        return await _run_qlik([
            "raw", "put", f"v1/apps/{resource_id}/space",
            "--body", json.dumps({"spaceId": space_id}),
        ])
    return f"Error: unsupported resource type '{resource_type}' for recycle bin move."


# ---------------------------------------------------------------------------
# Generic tools
# ---------------------------------------------------------------------------

@mcp.tool()
async def qlikcloud_get(path: str, query_params: Optional[str] = None) -> str:
    """Send a GET request to a Qlik Cloud API endpoint via qlik raw.

    Args:
        path: API path, e.g. v1/spaces
        query_params: Optional query string, e.g. "limit=10&type=shared"
    """
    args = ["raw", "get", path]
    if query_params:
        for pair in query_params.split("&"):
            args += ["--query", pair.strip()]
    return await _run_qlik(args)


@mcp.tool()
async def qlikcloud_post(path: str, body: str) -> str:
    """Send a POST request to a Qlik Cloud API endpoint via qlik raw.

    Args:
        path: API path, e.g. v1/spaces
        body: JSON body as a string, e.g. '{"name": "My Space", "type": "shared"}'
    """
    try:
        json.loads(body)
    except json.JSONDecodeError as e:
        return f"Error: body is not valid JSON: {e}"
    return await _run_qlik(["raw", "post", path, "--body", body])


@mcp.tool()
async def qlikcloud_put(path: str, body: str) -> str:
    """Send a PUT request to a Qlik Cloud API endpoint via qlik raw.

    IMPORTANT: PUT overwrites the existing resource. Before calling this tool,
    show the user what will be changed and the full body that will be sent,
    and wait for explicit confirmation.

    Args:
        path: API path, e.g. v1/spaces/abc123
        body: JSON body as a string
    """
    try:
        json.loads(body)
    except json.JSONDecodeError as e:
        return f"Error: body is not valid JSON: {e}"
    return await _run_qlik(["raw", "put", path, "--body", body])


@mcp.tool()
async def qlikcloud_delete(path: str) -> str:
    """Delete a Qlik Cloud resource via qlik raw.

    Supported resources and their governance behaviour:
    - Apps (v1/apps/...): moved to the Recycle Bin shared space, never hard-deleted.
    - Automations (v1/automations/...): hard-deleted after confirmation.
    - Data files (v1/data-files/...): hard-deleted after confirmation.
    - Spaces (v1/spaces/...): blocked. Must be deleted manually in the
      Qlik Cloud Management Console.
    - All other resource types: not supported by this tool.

    IMPORTANT: Before calling this tool, tell the user exactly what will be
    deleted and wait for explicit confirmation.

    Args:
        path: API path, e.g. v1/automations/abc123
    """
    normalized = path.strip().lstrip("/")

    # --- Spaces: blocked ---
    if normalized.startswith("v1/spaces"):
        return (
            "Blocked: space deletion is not permitted through this tool. "
            "Spaces must be deleted manually in the Qlik Cloud Management Console."
        )

    # --- Apps: recycle bin ---
    resource_type, resource_id = _detect_recycle_bin_resource(normalized)
    if resource_type:
        name = await _resolve_name(resource_id, resource_type)
        space_id, err = await _find_recycle_bin()
        if err:
            return err
        result = await _move_to_recycle_bin(resource_type, resource_id, space_id)
        if result.startswith("Error"):
            return result
        return (
            f"'{name}' ({resource_id}) has been moved to '{RECYCLE_BIN_NAME}'. "
            "It is no longer visible to end users but has not been hard-deleted."
        )

    # --- Automations and data files: hard delete ---
    if normalized.startswith("v1/automations/") or normalized.startswith("v1/data-files/"):
        return await _run_qlik(["raw", "delete", path])

    # --- Everything else: not supported ---
    return (
        "Blocked: this resource type is not supported by this tool. "
        "Supported: apps (recycle bin), automations, and data files."
    )


def _detect_recycle_bin_resource(normalized: str) -> tuple[str, str] | tuple[None, None]:
    """Return (resource_type, resource_id) for paths that use the recycle bin flow."""
    segments = normalized.split("/")
    if normalized.startswith("v1/apps/") and len(segments) > 2:
        return "app", segments[2]
    return None, None


if __name__ == "__main__":
    if not QLIK_API_KEY:
        print(
            "Warning: QLIK_API_KEY not set in .env - relying on qlik-cli configured context.",
            file=sys.stderr,
        )
    mcp.run(transport="stdio")
