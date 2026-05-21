# Release Checklist

Use this checklist before publishing `aa-mcp` to PyPI.

## Preflight

1. Confirm `pyproject.toml` has the intended `version`.
2. Confirm `README.md` renders correctly and lists all supported MCP tools.
3. Confirm no secrets, local snapshots, or `.env` files are staged.
4. Confirm `ARTIFICIAL_ANALYSIS_API_KEY` is only documented as an environment variable.

## Verification

Run the full local gate:

```bash
uv sync --dev
uv run pytest
uv run ruff check .
uv build
uv run twine check dist/*
```

For a local MCP smoke test:

```bash
export ARTIFICIAL_ANALYSIS_API_KEY="aa_your_key_here"
uv run aa-mcp-server
```

## Publish

Publish only after the verification commands pass and the PyPI credentials are configured locally.

```bash
uv run twine upload dist/*
```

## Post-Publish

Validate that the package can be launched through `uvx`:

```bash
ARTIFICIAL_ANALYSIS_API_KEY="aa_your_key_here" uvx aa-mcp
```
