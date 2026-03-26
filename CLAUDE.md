# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This project is a **local MCP (Model Context Protocol) server** that allows Claude Desktop to interact with a Qlik Cloud tenant using `qlik-cli` as the backend.

```
Claude Desktop -> MCP server (local) -> qlik-cli -> Qlik Cloud tenant
```

## Stack

- Python + FastMCP (`mcp[cli]`)
- API key via `.env` (loaded with `python-dotenv`)

## Setup & Run

```bash
pip install -r requirements.txt
cp .env.example .env        # then fill in QLIK_API_KEY
python server.py             # runs MCP server over stdio
```

## Architecture Requirements

- `qlik-cli` is already installed and configured with a context pointing to the Qlik Cloud tenant
- Use `qlik raw` for all HTTP calls - it covers any QPS endpoint without relying on explicit qlik-cli commands
  - Reference: https://qlik.dev/toolkits/qlik-cli/raw/raw/
  - Paths must omit the `/api` prefix: e.g. `v1/spaces`, not `/api/v1/spaces`
- Expose MCP tools for HTTP methods: GET, POST, PUT, DELETE
- The MCP server must invoke the `qlik` binary from the system PATH

## Important Constraints

- API reference is **qlik.dev** only - do NOT use `help.qlik.com` endpoints (those are Qlik Sense on-prem: Repository, Proxy, QRS)
- On Windows with PowerShell 5.x, enforce TLS 1.2 for any direct HTTP calls
- API Key must be managed securely (env var approach preferred over hardcoding)
