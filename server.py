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
QLIK_TENANT_URL = os.getenv("QLIK_TENANT_URL", "").rstrip("/")
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
    if resource_type == "automation":
        return await _run_qlik([
            "raw", "post", f"v1/automations/{resource_id}/actions/change-space",
            "--body", json.dumps({"spaceId": space_id}),
        ])
    if resource_type == "datafile":
        raw = await _run_qlik([
            "raw", "post", "v1/data-files/actions/change-space",
            "--body", json.dumps({"change-space": [{"id": resource_id, "spaceId": space_id}]}),
        ])
        if raw.startswith("Error"):
            return raw
        # 207 Multi-Status: inspect per-item result
        try:
            items = json.loads(raw).get("data", [])
            if items and items[0].get("status", 200) >= 400:
                detail = items[0].get("detail") or items[0].get("title", "unknown error")
                return f"Error: data file move failed: {detail}"
        except (json.JSONDecodeError, AttributeError):
            pass
        return raw
    return f"Error: unsupported resource type '{resource_type}' for recycle bin move."


# ---------------------------------------------------------------------------
# Generic tools
# ---------------------------------------------------------------------------

@mcp.tool()
async def qlikcloud_get(path: str, query_params: Optional[str] = None) -> str:
    """Send a GET request to a Qlik Cloud API endpoint via qlik raw.

    Use this only when no tool in the official Qlik MCP Server covers the
    operation. Prefer Qlik MCP tools for analytics operations such as opening
    apps, searching fields, listing sheets, or reading app content.

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

    Use this only when no tool in the official Qlik MCP Server covers the
    operation. Prefer Qlik MCP tools for analytics operations such as opening
    apps, searching fields, listing sheets, or reading app content.

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

    Use this only when no tool in the official Qlik MCP Server covers the
    operation. Prefer Qlik MCP tools for analytics operations such as opening
    apps, searching fields, listing sheets, or reading app content.

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
    - Automations (v1/automations/...): moved to the Recycle Bin shared space.
    - Data files (v1/data-files/...): moved to the Recycle Bin shared space.
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
    if normalized.startswith("v1/automations/") and len(segments) > 2:
        return "automation", segments[2]
    if normalized.startswith("v1/data-files/") and len(segments) > 2:
        return "datafile", segments[2]
    return None, None


@mcp.tool()
async def qlikcloud_assistant_chat(
    assistant_id: str,
    message: str,
    thread_id: Optional[str] = None,
) -> str:
    """Send a message to a Qlik Answers assistant and get a response.

    Maintains conversation context across calls by reusing the same thread.
    On the first call, omit thread_id and a new thread is created automatically.
    Pass the returned thread_id on subsequent calls to continue the conversation.

    Args:
        assistant_id: ID of the assistant to query (use qlikcloud_get with path v1/assistants to list them)
        message: The question or message to send
        thread_id: Optional thread ID from a previous call to continue the conversation
    """
    # Create a thread if none provided
    if not thread_id:
        raw = await _run_qlik([
            "raw", "post", f"v1/assistants/{assistant_id}/threads",
            "--body", "{}",
        ])
        if raw.startswith("Error"):
            return raw
        try:
            thread_id = json.loads(raw)["id"]
        except (json.JSONDecodeError, KeyError):
            return f"Error: could not create thread: {raw}"

    # Post the interaction
    raw = await _run_qlik([
        "raw", "post", f"v1/assistants/{assistant_id}/threads/{thread_id}/interactions",
        "--body", json.dumps({"prompt": message}),
    ])
    if raw.startswith("Error"):
        return raw
    try:
        data = json.loads(raw)
        content = data.get("response", {}).get("content", "")
        if not content:
            return f"Error: no response content in: {raw}"
        return f"[thread_id: {thread_id}]\n\n{content}"
    except (json.JSONDecodeError, AttributeError):
        return f"Error: could not parse interaction response: {raw}"


async def _get_space_name(space_id: str) -> str:
    """Resolve a space ID to its display name, falling back to the ID on error."""
    raw = await _run_qlik(["raw", "get", f"v1/spaces/{space_id}"])
    if raw.startswith("Error"):
        return space_id
    try:
        return json.loads(raw).get("name", space_id)
    except (json.JSONDecodeError, AttributeError):
        return space_id


def _dataset_table_name(dataset_name: str) -> str:
    """Strip common file extensions to derive a Qlik table name."""
    for ext in (".csv", ".txt", ".qvd", ".xlsx", ".xls"):
        if dataset_name.lower().endswith(ext):
            return dataset_name[: -len(ext)]
    return dataset_name


def _build_csv_format(load_options: dict) -> str:
    """Build the Qlik format string from qDataFormat metadata."""
    q = load_options.get("qDataFormat", {})
    parts = []
    if q.get("qType") == "CSV":
        parts.append("txt")
    if q.get("qCodePage") == 65001:
        parts.append("utf8")
    label = q.get("qLabel", "")
    if label:
        parts.append(label)
    quote = q.get("qQuote", "")
    if quote and quote.lower() not in ("", "none"):
        parts.append(quote)
    delim_code = q.get("qDelimiter", {}).get("qScriptCode", "")
    if delim_code:
        parts.append(f"delimiter is {delim_code}")
    return ", ".join(parts)


def _generate_dataset_script(dataset: dict, space_name: str) -> str:
    """Generate a Qlik LOAD script section for a single dataset."""
    store_type = (
        dataset.get("dataAssetInfo", {}).get("dataStoreInfo", {}).get("type", "")
    )
    technical_name = dataset.get("technicalName", "")
    ds_name = dataset.get("name", "unknown")
    table_name = _dataset_table_name(ds_name)
    fields = sorted(
        dataset.get("schema", {}).get("dataFields", []),
        key=lambda x: x.get("index", 0),
    )
    field_list = ",\n".join(f"    [{f['name']}]" for f in fields)

    if store_type == "qix-datafiles":
        fmt = _build_csv_format(dataset.get("schema", {}).get("loadOptions", {}))
        lib_path = f"lib://{space_name}:DataFiles/{technical_name}"
        return f"[{table_name}]:\nLOAD\n{field_list}\nFROM [{lib_path}]\n({fmt});\n"

    ds_type = dataset.get("type", "unknown")
    return (
        f"// TODO: '{ds_name}' (type={ds_type}, store={store_type})"
        " - script generation not yet supported for this source type\n"
    )


@mcp.tool()
async def qlikcloud_create_app_from_data_product(
    app_name: str,
    data_product_name: Optional[str] = None,
    data_product_id: Optional[str] = None,
    space_id: Optional[str] = None,
) -> str:
    """Create a new Qlik app with a load script generated from a Data Product.

    Fetches all datasets in the data product, generates a LOAD script section
    for each one, creates an empty app, and sets the script. No Data Manager
    involvement - the script is written directly from dataset metadata.

    Supported source types: DataFiles (CSV, delimited text).
    Other source types (e.g. Snowflake) generate a TODO comment placeholder.

    Provide either data_product_name (searched by name) or data_product_id
    (skips the lookup). If a name search returns more than one match, the tool
    returns the list and asks you to supply the ID instead.

    Args:
        app_name: Name for the new app
        data_product_name: Data product name to search for (case-insensitive partial match)
        data_product_id: Data product ID (from data-governance/data-products) - skips name lookup
        space_id: Space ID to create the app in (defaults to personal space if omitted)
    """
    if not data_product_name and not data_product_id:
        return "Error: provide either data_product_name or data_product_id."

    # --- Resolve data product ID from name ---
    if not data_product_id:
        raw = await _run_qlik([
            "raw", "get", "v1/items",
            "--query", "resourceType=dataproduct",
            "--query", f"query={data_product_name}",
        ])
        if raw.startswith("Error"):
            return raw
        try:
            parsed = json.loads(raw)
            items = parsed if isinstance(parsed, list) else parsed.get("data", [])
        except (json.JSONDecodeError, AttributeError):
            return f"Error: could not parse items response: {raw}"

        if not items:
            return f"Error: no data product found matching '{data_product_name}'."
        if len(items) > 1:
            matches = "\n".join(f"  {i['name']} (id: {i['resourceId']})" for i in items)
            return (
                f"Multiple data products match '{data_product_name}'. "
                f"Supply data_product_id instead:\n{matches}"
            )
        data_product_id = items[0]["resourceId"]

    # --- Fetch dataset IDs from the data product ---
    raw = await _run_qlik(["raw", "get", f"data-governance/data-products/{data_product_id}"])
    if raw.startswith("Error"):
        return raw
    try:
        dp = json.loads(raw)
        dataset_ids = dp.get("datasetIds", [])
    except (json.JSONDecodeError, AttributeError):
        return f"Error: could not parse data product response: {raw}"

    if not dataset_ids:
        return f"Error: data product '{data_product_id}' has no datasets."

    # --- Fetch metadata for each dataset and generate script sections ---
    script_sections = []
    skipped = []
    space_name_cache: dict[str, str] = {}

    for ds_id in dataset_ids:
        raw = await _run_qlik(["raw", "get", f"data-governance/data-sets/{ds_id}"])
        if raw.startswith("Error"):
            skipped.append(f"{ds_id} (fetch failed: {raw})")
            continue
        try:
            dataset = json.loads(raw)
        except json.JSONDecodeError:
            skipped.append(f"{ds_id} (parse failed)")
            continue

        ds_space_id = dataset.get("spaceId", "")
        if ds_space_id not in space_name_cache:
            space_name_cache[ds_space_id] = await _get_space_name(ds_space_id)
        space_name = space_name_cache[ds_space_id]

        script_sections.append(_generate_dataset_script(dataset, space_name))

    if not script_sections:
        return "Error: could not generate script for any dataset in this data product."

    full_script = "\n".join(script_sections)

    # --- Create the app ---
    app_body: dict = {"attributes": {"name": app_name}}
    if space_id:
        app_body["attributes"]["spaceId"] = space_id
    raw = await _run_qlik(["raw", "post", "v1/apps", "--body", json.dumps(app_body)])
    if raw.startswith("Error"):
        return raw
    try:
        app_id = json.loads(raw)["attributes"]["id"]
    except (json.JSONDecodeError, KeyError):
        return f"Error: could not parse app creation response: {raw}"

    # --- Set the script ---
    raw = await _run_qlik([
        "raw", "post", f"v1/apps/{app_id}/scripts",
        "--body", json.dumps({"script": full_script}),
    ])
    if raw.startswith("Error"):
        return (
            f"App '{app_name}' created (id: {app_id}) but script could not be set: {raw}\n"
            f"Script content:\n{full_script}"
        )

    result = [f"App '{app_name}' created (id: {app_id}). Script set with {len(script_sections)} dataset(s)."]
    if skipped:
        result.append(f"Skipped {len(skipped)} dataset(s): {skipped}")
    return "\n".join(result)


if __name__ == "__main__":
    if not QLIK_API_KEY:
        print(
            "Warning: QLIK_API_KEY not set in .env - relying on qlik-cli configured context.",
            file=sys.stderr,
        )
    mcp.run(transport="stdio")
