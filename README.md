# Qlik Cloud Admin MCP Server

> **Demo and experimental use only.**
> This project is provided as-is to illustrate concepts. It is not production-ready,
> not officially supported by Qlik, and carries no warranty of any kind.
> Anyone using this code does so at their own risk and is responsible for testing
> and validating it in their own environment before use.

---

## What This Is

A local [Model Context Protocol](https://modelcontextprotocol.io) (MCP) server that connects
Claude Desktop to a Qlik Cloud tenant for admin operations.

```
Claude Desktop -> MCP server (this project) -> qlik-cli -> Qlik Cloud tenant
```

It demonstrates two things:

1. **Extensibility** - Qlik Cloud exposes a rich REST API. By wrapping it in an MCP server,
   any admin operation becomes available as a natural language conversation in Claude Desktop.

2. **Governance** - MCP tools can encode business rules. This server shows a concrete example:
   deleting a resource does not hard-delete it. Instead, it moves it to a "Recycle Bin"
   shared space, giving admins a recovery window. Deleting spaces is blocked entirely and
   redirected to the Qlik Cloud Management Console.

This server complements the official [Qlik MCP Server](https://help.qlik.com/en-US/cloud-services/Subsystems/Hub/Content/Sense_Hub/QlikMCP/Qlik-MCP-server-tools.htm),
which covers analytics operations. This one covers admin and governance operations that the
official server does not expose today.

---

## Prerequisites

- [uv](https://docs.astral.sh/uv/) installed on your machine
- [qlik-cli](https://qlik.dev/toolkits/qlik-cli/) installed and configured with a context
  pointing to your Qlik Cloud tenant
- A [Qlik Cloud API key](https://help.qlik.com/en-US/cloud-services/Subsystems/Hub/Content/Sense_Hub/Admin/mc-generate-api-keys.htm) with tenant admin permissions
- Claude Desktop

---

## Setup

### 1. Install uv

```powershell
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### 2. Download this repository

```powershell
git clone https://github.com/mabaeyens/qlik-cloud-admin-mcp.git
cd qlik-cloud-admin-mcp
```

Or download the ZIP from GitHub and extract it.

### 3. Add your API key

```powershell
copy .env.example .env
```

Open `.env` and set your key:

```
QLIK_API_KEY=your_api_key_here
```

If you leave it empty, the server falls back to the credentials in your qlik-cli context.

### 4. Create the Recycle Bin space

In Qlik Cloud, create a **shared space** named exactly `Recycle Bin`. Restrict membership
to admins only. The delete tool will move apps, automations, and data files there instead
of hard-deleting them.

### 5. Configure Claude Desktop

Open `%APPDATA%\Claude\claude_desktop_config.json` and add the following block inside
`mcpServers`. Replace the path with the actual path where you extracted the repository.

```json
{
  "mcpServers": {
    "qlik-cloud-admin": {
      "command": "uv",
      "args": [
        "--directory",
        "C:/path/to/qlik-cloud-admin-mcp",
        "run",
        "server.py"
      ],
      "env": {
        "QLIK_API_KEY": "your_api_key_here"
      }
    }
  }
}
```

You can set the API key either in `.env` or in the `env` block above. The `.env` file takes
precedence if both are set.

### 6. Restart Claude Desktop

Fully quit and reopen Claude Desktop. The server should appear under Settings > Connectors.

---

## Tools

| Tool | Description |
|---|---|
| `qlikcloud_get` | GET any Qlik Cloud REST endpoint |
| `qlikcloud_post` | POST to any Qlik Cloud REST endpoint |
| `qlikcloud_put` | PUT to any Qlik Cloud REST endpoint (asks for confirmation) |
| `qlikcloud_delete` | DELETE with governance rules enforced (see below) |

### Governance rules in qlikcloud_delete

- **Apps** - moved to the "Recycle Bin" shared space, never hard-deleted.
- **Automations** - moved to the "Recycle Bin" shared space, never hard-deleted.
- **Data files** - moved to the "Recycle Bin" shared space, never hard-deleted.
- **Spaces** - blocked. Must be deleted manually in the Qlik Cloud Management Console.
- **All other resource types** - not supported by this tool.

---

## API Path Format

Paths follow the `qlik raw` convention and omit the `/api` prefix:

```
v1/spaces          (not /api/v1/spaces)
v1/users/me
v1/apps/{appId}
```

Reference: https://qlik.dev/toolkits/qlik-cli/raw/raw/

---

## Next Steps

- **Ownership transfer on retirement** - when a resource is moved to the Recycle Bin,
  also reassign its ownership to the admin account to prevent the original owner from
  restoring it without admin involvement.

- **Personal space resources** - resources with no `spaceId` (personal space) may behave
  differently or fail when moved via the current API endpoints. This needs dedicated
  handling before the tool can be considered reliable for all resources.

---

## License

MIT
