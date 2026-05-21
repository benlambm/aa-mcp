# aa-mcp

MCP server wrapping the [Artificial Analysis](https://artificialanalysis.ai/) public API.
Enables AI agents to query LLM and multimodal model benchmarks, pricing, speed data, and track model updates via structured diffs.

The PyPI package is `aa-mcp`; it installs both `aa-mcp` and `aa-mcp-server`
console commands.

## Requirements

- Python 3.10+
- [uv](https://docs.astral.sh/uv/) (for installation and running)
- An Artificial Analysis API key ([get one free](https://artificialanalysis.ai/account))

## Installation & Running

### Run from PyPI with uvx

After the package is published:

```bash
export ARTIFICIAL_ANALYSIS_API_KEY="aa_your_key_here"
uvx aa-mcp
```

### Run directly from a local checkout with uvx

```bash
# Set your API key
export ARTIFICIAL_ANALYSIS_API_KEY="aa_your_key_here"

# Run the MCP server from a local path (stdio transport)
uvx --from /path/to/aa-mcp-server aa-mcp-server
```

### Run from source (development)

```bash
cd aa-mcp-server
uv sync
uv run aa-mcp-server
```

### Run with uvx from a local directory

```bash
uvx --from ./aa-mcp-server aa-mcp-server
```

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `ARTIFICIAL_ANALYSIS_API_KEY` | Yes | - | Your AA API key |
| `AA_MCP_SNAPSHOT_DIR` | No | `~/.local/share/aa-mcp/snapshots/` | Directory for update snapshots |
| `AA_MCP_LOG_LEVEL` | No | `INFO` | Log level (DEBUG, INFO, WARNING, ERROR) |

## Official API Coverage

This server wraps the current free Artificial Analysis API endpoints documented at
<https://artificialanalysis.ai/api-reference>:

| Artificial Analysis endpoint | MCP tool |
|---|---|
| `GET /api/v2/data/llms/models` | `aa_list_llms`, `aa_get_model`, `aa_compare_models`, `aa_list_recent_updates`, `aa_healthcheck` |
| `GET /api/v2/data/media/text-to-image` | `aa_list_media_models(modality="text-to-image")` |
| `GET /api/v2/data/media/image-editing` | `aa_list_media_models(modality="image-editing")` |
| `GET /api/v2/data/media/text-to-speech` | `aa_list_media_models(modality="text-to-speech")` |
| `GET /api/v2/data/media/text-to-video` | `aa_list_media_models(modality="text-to-video")` |
| `GET /api/v2/data/media/image-to-video` | `aa_list_media_models(modality="image-to-video")` |
| `POST /api/v2/critpt/evaluate` | `aa_evaluate_critpt` |

## MCP Tools

### `aa_list_llms`
List LLM models with filtering and sorting.

- **Filters**: `creator`, `name`, `slug` (substring match)
- **Sort by**: `intelligence` (default), `price`, `speed`, `ttft`, `coding`, `math`
- **`limit`**: Max results (default 20)

### `aa_get_model`
Get full details for a single model by id, slug, or name.

- Returns candidates if multiple matches found
- Supports partial/fuzzy matching

### `aa_compare_models`
Side-by-side comparison of 2+ models.

- Compares: intelligence, coding, math, pricing, speed, latency
- Returns rankings across all metrics
- Input: list of identifiers (ids, slugs, or names)

### `aa_list_recent_updates`
Detect changes since the last local snapshot.

- **New models**: present in current data but not in snapshot
- **Removed models**: present in snapshot but gone from current data
- **Changed models**: field-level diffs for pricing, speed, intelligence scores, etc.
- First run creates a baseline snapshot
- Float changes below 0.01 threshold are ignored (noise filtering)

### `aa_list_media_models`
Query multimodal / media model rankings.

- **Modalities**: `text-to-image`, `image-editing`, `text-to-speech`, `text-to-video`, `image-to-video`
- **`top_n`**: Limit results (default 10)
- **`include_categories`**: Per-category Elo breakdown where the upstream endpoint supports it

### `aa_evaluate_critpt`
Submit a complete CritPt benchmark batch to the official evaluation endpoint.

- Requires `submissions` for the full public CritPt problem set
- Validates required fields before sending: `problem_id`, `generated_code`, `model`, `generation_config`
- Optional `batch_metadata` object is passed through to Artificial Analysis
- The upstream endpoint is rate-limited separately and may take substantial time to complete

### `aa_healthcheck`
Verify API key and upstream connectivity.

- Returns masked key preview, model count, rate limit info
- Reports specific error types (auth, rate limit, server error)

## Snapshot / Update Tracking

The `aa_list_recent_updates` tool uses a local JSON snapshot mechanism:

1. **First call**: Fetches all LLM models, saves a normalized snapshot to disk, reports "baseline created"
2. **Subsequent calls**: Fetches fresh data, diffs against the latest snapshot, reports changes
3. **Snapshot location**: `~/.local/share/aa-mcp/snapshots/llm_models_YYYYMMDDTHHMMSSZ.json`
4. **Noise filtering**: Float fields use a 0.01 threshold to avoid reporting insignificant fluctuations
5. **Tracked fields**: name, slug, creator, all evaluation scores, all pricing fields, speed/latency

## opencode Integration

Add to your `opencode.json`:

```json
{
  "mcp": {
    "servers": {
      "artificial-analysis": {
        "command": "uvx",
        "args": ["--from", "/path/to/aa-mcp-server", "aa-mcp-server"],
        "env": {
          "ARTIFICIAL_ANALYSIS_API_KEY": "aa_your_key_here"
        }
      }
    }
  }
}
```

For PyPI and local-checkout MCP client examples, see
[`docs/mcp-client-config.md`](docs/mcp-client-config.md).

## Example Usage (via MCP client)

```
# List top 5 most intelligent LLMs
aa_list_llms(sort_by="intelligence", limit=5)

# Get details on Claude 3.5 Sonnet
aa_get_model("claude-3-5-sonnet")

# Compare GPT-4o vs Claude 3.5 Sonnet vs Gemini 1.5 Pro
aa_compare_models(["gpt-4o", "claude-3-5-sonnet", "gemini-1.5-pro"])

# Check for recent model changes
aa_list_recent_updates()

# Top 5 text-to-image models
aa_list_media_models(modality="text-to-image", top_n=5)

# Submit CritPt benchmark results
aa_evaluate_critpt(
  submissions=[
    {
      "problem_id": "Challenge_1_main",
      "generated_code": "def solution(): return 42",
      "model": "example-model",
      "generation_config": {"temperature": 0}
    }
  ],
  batch_metadata={"run_id": "local-test"}
)

# Verify API connectivity
aa_healthcheck()
```

## Development Checks

```bash
uv sync --dev
uv run pytest
uv run ruff check .
uv build
uv run twine check dist/*
```

## Known Limitations

- **Free API tier**: 1000 requests/day rate limit
- **No explicit "updated_at" field**: Update detection relies on snapshot diffs, not API metadata
- **LLM data only for snapshots**: Media model snapshot tracking is not yet implemented
- **CritPt completeness**: The upstream evaluation API requires submissions for the full public problem set; this server validates object shape but cannot verify set completeness locally
- **No pagination**: The free API returns all models in a single response; no cursor/offset support
- **Snapshot storage**: Local filesystem only; no cloud sync

## Attribution

Data from [Artificial Analysis](https://artificialanalysis.ai/). Attribution required per their terms.
