# Repository Guidelines

## Project Structure & Module Organization

This is a Python MCP server package using a `src` layout. Core code lives in `src/aa_mcp/`:

- `server.py`: FastMCP tool definitions and CLI entry point.
- `client.py`: Artificial Analysis API client and API error types.
- `snapshot.py`: local snapshot persistence, normalization, and diff formatting.
- `__init__.py`: package metadata surface.

Project metadata and packaging configuration are in `pyproject.toml`; dependency locking is in `uv.lock`. There is currently no committed `tests/` directory, so add one when introducing automated coverage.

## Build, Test, and Development Commands

Use `uv` for all Python workflows.

- `uv sync`: install locked dependencies for local development.
- `uv run aa-mcp-server`: run the MCP server from source using stdio transport.
- `uv build`: build source and wheel distributions.
- `uv run pytest`: run the test suite once tests are added.

For manual server checks, set `ARTIFICIAL_ANALYSIS_API_KEY` before launching:

```bash
export ARTIFICIAL_ANALYSIS_API_KEY="aa_your_key_here"
uv run aa-mcp-server
```

## Coding Style & Naming Conventions

Target Python 3.10+. Use type hints for public helpers and tool functions. Keep modules small and purpose-specific, following the existing split between server orchestration, API access, and snapshot logic.

Use `snake_case` for functions, variables, and modules; `PascalCase` for exception and class names. MCP tool names should keep the existing `aa_` prefix, for example `aa_healthcheck`. Prefer official Artificial Analysis API field names in returned data and transformation code.

## Testing Guidelines

Add tests under `tests/` with filenames like `test_client.py` or `test_snapshot.py`. Focus unit tests on API error handling, model matching, sorting behavior, snapshot normalization, and diff output. Mock HTTP calls rather than relying on the live Artificial Analysis API. Run tests with:

```bash
uv run pytest
```

## Commit & Pull Request Guidelines

Recent commits use Conventional Commit prefixes such as `feat:`, `fix:`, and `refactor:`. Keep subjects imperative and scoped, for example `fix: handle AA rate limit responses`.

Pull requests should include a short summary, test results, and any environment or API-key assumptions. Link related issues when available. For behavior changes, include example MCP tool inputs and representative output.

## Security & Configuration Tips

Never commit API keys or generated local snapshots. Configure secrets through environment variables, especially `ARTIFICIAL_ANALYSIS_API_KEY`. Snapshot output defaults to `~/.local/share/aa-mcp/snapshots/`; keep test fixtures separate from real user data.
