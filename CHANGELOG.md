# Changelog

## v0.2.0 - 2026-04-01

### Added
- `qlikcloud_create_app_from_data_product` - creates a Qlik app with a load script generated
  directly from Data Product metadata. Fetches dataset schemas from the data-governance API,
  resolves source paths and field lists, and sets the script via the apps REST API. No Data
  Manager involvement. Supported source types: DataFiles (CSV/delimited). Other source types
  produce `// TODO` placeholders.
- `QLIK_TENANT_URL` env var (required by the above tool).
- `qlikcloud_assistant_chat` - query a Qlik Answers assistant with conversation context.
  Creates a thread on the first call; pass the returned `thread_id` to continue the conversation.

### Changed
- Generic REST tools (`qlikcloud_get`, `qlikcloud_post`, `qlikcloud_put`) now include explicit
  fallback language in their descriptions so Claude prefers the official Qlik MCP Server for
  analytics operations when both servers are connected.
- Setup step 7 added to README: system prompt recommendation for dual-MCP setups.
- `mcp-config-example.json` updated to use `uv` instead of a direct Python path.

---

## v0.1.0 - 2026-03-31

Initial release.

### Added
- `qlikcloud_get` / `qlikcloud_post` / `qlikcloud_put` - generic REST tools for any Qlik
  Cloud API endpoint via `qlik raw`.
- `qlikcloud_delete` - governance-aware delete. Apps, automations, and data files are moved
  to a "Recycle Bin" shared space instead of being hard-deleted. Space deletion is blocked.
- Recycle Bin pattern documented in README with setup instructions.
- `uv`-based packaging and distribution.
- `.env` / `QLIK_API_KEY` support with fallback to qlik-cli context credentials.
