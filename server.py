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
RECYCLE_BIN_NAME = "App Recycle Bin"


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

    Governance rules enforced by resource type:
    - Apps (v1/apps/...): never hard-deleted. Moved to the App Recycle Bin space
      so admins have a recovery window.
    - Spaces (v1/spaces/...): blocked. Spaces must be deleted manually in the
      Qlik Cloud Management Console.
    - All other resources: deleted after user confirmation.

    IMPORTANT: Before calling this tool, tell the user exactly what will be
    deleted and wait for explicit confirmation.

    Args:
        path: API path, e.g. v1/datasets/abc123
    """
    normalized = path.strip().lstrip("/")

    # --- Spaces: blocked ---
    if normalized.startswith("v1/spaces"):
        return (
            "Blocked: space deletion is not permitted through this tool. "
            "Spaces must be deleted manually in the Qlik Cloud Management Console."
        )

    # --- Apps: recycle bin flow ---
    if normalized.startswith("v1/apps"):
        app_id = normalized.split("/")[2] if len(normalized.split("/")) > 2 else None
        if not app_id:
            return "Error: could not extract app ID from path."

        # Resolve app name
        items_raw = await _run_qlik([
            "raw", "get", "v1/items",
            "--query", f"resourceId={app_id}",
            "--query", "resourceType=app",
        ])
        if not items_raw.startswith("Error"):
            try:
                items = json.loads(items_raw).get("data", [])
                app_name = items[0].get("name", app_id) if items else app_id
            except json.JSONDecodeError:
                app_name = app_id
        else:
            app_name = app_id

        # Find recycle bin
        spaces_raw = await _run_qlik(["raw", "get", "v1/spaces", "--query", f"name={RECYCLE_BIN_NAME}"])
        if spaces_raw.startswith("Error"):
            return spaces_raw
        try:
            spaces_data = json.loads(spaces_raw)
        except json.JSONDecodeError:
            return f"Error: could not parse spaces response: {spaces_raw}"

        matches = [s for s in spaces_data.get("data", []) if s.get("name") == RECYCLE_BIN_NAME]
        if not matches:
            return (
                f"Recycle bin not found: no space named '{RECYCLE_BIN_NAME}' exists. "
                "Create a managed space with that name restricted to admins, then retry."
            )

        body = json.dumps({"spaceId": matches[0]["id"]})
        result = await _run_qlik(["raw", "put", f"v1/apps/{app_id}/space", "--body", body])
        if result.startswith("Error"):
            return result

        return (
            f"App '{app_name}' ({app_id}) has been moved to '{RECYCLE_BIN_NAME}'. "
            "It is no longer visible to end users but has not been hard-deleted."
        )

    # --- Everything else: proceed ---
    return await _run_qlik(["raw", "delete", path])


if __name__ == "__main__":
    if not QLIK_API_KEY:
        print(
            "Warning: QLIK_API_KEY not set in .env - relying on qlik-cli configured context.",
            file=sys.stderr,
        )
    mcp.run(transport="stdio")
