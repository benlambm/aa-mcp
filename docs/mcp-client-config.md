# MCP Client Configuration

`aa-mcp` installs an MCP stdio command and reads its Artificial
Analysis API key from the environment. Do not put API keys in source control.

## Published PyPI Package

Use this configuration after the package is available on PyPI:

```json
{
  "mcp": {
    "servers": {
      "artificial-analysis": {
        "command": "uvx",
        "args": ["--from", "aa-mcp", "aa-mcp-server"],
        "env": {
          "ARTIFICIAL_ANALYSIS_API_KEY": "aa_your_key_here"
        }
      }
    }
  }
}
```

## Local Checkout

Use this configuration while developing or testing an unpublished checkout:

```json
{
  "mcp": {
    "servers": {
      "artificial-analysis": {
        "command": "uvx",
        "args": ["--from", "/absolute/path/to/aa-mcp-server", "aa-mcp-server"],
        "env": {
          "ARTIFICIAL_ANALYSIS_API_KEY": "aa_your_key_here"
        }
      }
    }
  }
}
```

## Environment Variables

- `ARTIFICIAL_ANALYSIS_API_KEY`: required API key from Artificial Analysis.
- `AA_MCP_SNAPSHOT_DIR`: optional directory for model snapshots.
- `AA_MCP_LOG_LEVEL`: optional log level such as `INFO` or `DEBUG`.
