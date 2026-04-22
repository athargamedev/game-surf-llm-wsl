---
source: Context7 API
library: Chrome DevTools MCP
package: chrome-devtools-mcp
topic: installation-runtime-startup-and-target-session-troubleshooting
fetched: 2026-04-22T00:00:00Z
official_docs: https://github.com/chromedevtools/chrome-devtools-mcp
---

## Installation / runtime requirements

- Requires **Node.js v20.19+** (or newer latest maintenance LTS), **npm**, and **current stable Chrome or newer**.
- Typical local MCP startup uses **npx**.
- Optional startup args documented for command-based configs include `--headless`, `--isolated`, `--channel=...`, `--browser-url=http://127.0.0.1:9222`, and `--autoConnect`.

## Verify the MCP server starts correctly

Use this first:

```bash
npx chrome-devtools-mcp@latest --help
```

If needed, run with verbose logging:

```bash
DEBUG=* npx chrome-devtools-mcp@latest --log-file=/path/to/chrome-devtools-mcp.log
```

Operational check: if `--help` runs, the package resolves and the Node environment is supported.

## Browser attachment prerequisites

- To attach to an existing browser, configure:

```json
{
  "command": "npx",
  "args": ["chrome-devtools-mcp@latest", "--browser-url=http://127.0.0.1:9222"]
}
```

- For **`--autoConnect`**, docs say it requires a **running Chrome >= M144** with **remote debugging enabled**.
- WSL docs show manually starting Chrome with remote debugging, then pointing MCP at `http://127.0.0.1:9222`.

## Common causes of `Target closed` / unavailable target-session errors

### `Target closed`
- Means the browser could not be started.
- Common fixes from docs:
  - close existing Chrome instances
  - ensure latest stable Chrome is installed
  - verify the system can actually launch Chrome

### Auto-connect target/session failures
- `Could not find DevToolsActivePort` is specifically tied to `--autoConnect`.
- Usual causes:
  - wrong Chrome version for auto-connect
  - remote debugging not enabled
  - sandbox/client isolation preventing discovery

### Sandboxing / unavailable session issues
- If the MCP client sandboxes the server (macOS Seatbelt / Linux containers), `chrome-devtools-mcp` may be unable to launch Chrome.
- Recommended workaround: disable sandboxing for this MCP server **or** start Chrome manually outside the sandbox and use `--browser-url`.

### Environment / install problems that look like startup failures
- `ERR_MODULE_NOT_FOUND` can indicate unsupported Node version or corrupted npm/npx cache.
- Docs recommend clearing `~/.npm/_npx` and cleaning npm cache if needed.

## Config guidance for local command-based startup with npx

Basic:

```json
{
  "mcpServers": {
    "chrome-devtools": {
      "command": "npx",
      "args": ["chrome-devtools-mcp@latest"]
    }
  }
}
```

Attach to existing Chrome (most reliable when local startup is restricted):

```json
{
  "mcpServers": {
    "chrome-devtools": {
      "command": "npx",
      "args": ["chrome-devtools-mcp@latest", "--browser-url=http://127.0.0.1:9222"]
    }
  }
}
```

Auto-connect:

```json
{
  "mcpServers": {
    "chrome-devtools": {
      "command": "npx",
      "args": ["chrome-devtools-mcp@latest", "--autoConnect"]
    }
  }
}
```

## Concise operational guidance

1. Confirm runtime first: Node 20.19+, npm, stable Chrome.
2. Run `npx chrome-devtools-mcp@latest --help` before debugging the MCP client.
3. If browser launch is flaky or sandboxed, prefer manually starting Chrome with remote debugging and use `--browser-url`.
4. Treat `Target closed` as a Chrome launch problem; treat `DevToolsActivePort` as an auto-connect / remote-debugging problem.
5. Use `DEBUG=*` logging when startup succeeds inconsistently.
