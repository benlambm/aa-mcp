# MCP Client Configuration

`aa-mcp` installs an MCP stdio command and reads its Artificial
Analysis API key from the environment. Do not put API keys in source control.

## Configuration

Use the published PyPI package through `uvx`:

```json
{
  "mcp": {
    "servers": {
      "artificial-analysis": {
        "command": "uvx",
        "args": ["aa-mcp"],
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
