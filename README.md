# aa-mcp

MCP server wrapping the [Artificial Analysis](https://artificialanalysis.ai/) public API.
Enables AI agents to query LLM and multimodal model benchmarks, pricing, speed data, and track model updates via structured diffs.

The PyPI package is `aa-mcp`; it installs the `aa-mcp` console command.

## Requirements

- Python 3.10+
- [uv](https://docs.astral.sh/uv/) (for installation and running)
- An Artificial Analysis API key ([get one free](https://artificialanalysis.ai/account))

## Installation & Running

Use `uvx` as the standard runtime path:

```bash
export ARTIFICIAL_ANALYSIS_API_KEY="aa_your_key_here"
uvx aa-mcp
```

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `ARTIFICIAL_ANALYSIS_API_KEY` | Yes | - | Your AA API key |
| `AA_MCP_SNAPSHOT_DIR` | No | `~/.local/share/aa-mcp/snapshots/` | Directory for update snapshots |
| `AA_MCP_LOG_LEVEL` | No | `INFO` | Log level (DEBUG, INFO, WARNING, ERROR) |
| `AA_MCP_CACHE_SECONDS` | No | `3600` | How long list results are reused within one server process (`0` disables) |

## Official API Coverage

This server wraps the Free-tier V2 endpoints documented at
<https://artificialanalysis.ai/data-api/docs>. They accept Free, Pro, and
Commercial keys. The legacy `/api/v2/data/*` routes retire on 2026-11-04
([migration guide](https://artificialanalysis.ai/data-api/migrate-v2-data)).

| Artificial Analysis endpoint | MCP tool |
|---|---|
| `GET /api/v2/language/models/free` | `aa_list_llms`, `aa_get_model`, `aa_compare_models`, `aa_list_recent_updates`, `aa_healthcheck` |
| `GET /api/v2/media/text-to-image/models/free` | `aa_list_media_models(modality="text-to-image")` |
| `GET /api/v2/media/image-editing/models/free` | `aa_list_media_models(modality="image-editing")` |
| `GET /api/v2/media/text-to-speech/models/free` | `aa_list_media_models(modality="text-to-speech")` |
| `GET /api/v2/media/text-to-video/models/free` | `aa_list_media_models(modality="text-to-video")` |
| `GET /api/v2/media/image-to-video/models/free` | `aa_list_media_models(modality="image-to-video")` |
| `GET /api/v2/media/text-to-video-audio/models/free` | `aa_list_media_models(modality="text-to-video-audio")` |
| `GET /api/v2/media/image-to-video-audio/models/free` | `aa_list_media_models(modality="image-to-video-audio")` |
| `GET /api/v2/media/speech-to-speech/models/free` | `aa_list_media_models(modality="speech-to-speech")` |
| `GET /api/v2/media/speech-to-text/models/free` | `aa_list_media_models(modality="speech-to-text")` |
| `GET /api/v2/media/music/instrumental/models/free` | `aa_list_media_models(modality="music-instrumental")` |
| `GET /api/v2/media/music/with-vocals/models/free` | `aa_list_media_models(modality="music-with-vocals")` |
| `POST /api/v2/critpt/evaluate` | `aa_evaluate_critpt` |

To keep tool output stable, the client maps V2 records back onto the legacy field
names: `performance.*` speeds are copied to top-level `median_*` fields, media
lists get `rank` from leaderboard order, and `price_1m_blended_3_to_1` is derived
as `(3 × input + output) / 4` because the Free tier no longer returns it.

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

- **Modalities**: `text-to-image`, `image-editing`, `text-to-speech`, `text-to-video`, `image-to-video`, `text-to-video-audio`, `image-to-video-audio`, `speech-to-speech`, `speech-to-text`, `music-instrumental`, `music-with-vocals`
- **`top_n`**: Limit results (default 10)
- **`include_categories`**: Pro tier only; Free rankings omit it and the response carries a `note`
- Speech-to-speech and speech-to-text are scored by benchmark (no Elo), so they have no `rank`

### `aa_evaluate_critpt`
Submit a complete CritPt benchmark batch to the official evaluation endpoint.

- Requires `submissions` for the full public CritPt problem set
- Validates required fields before sending: `problem_id`, `generated_code`, `model`, `generation_config`
- Optional `batch_metadata` object is passed through to Artificial Analysis
- The upstream endpoint is rate-limited separately and may take substantial time to complete

### `aa_healthcheck`
Verify API key and upstream connectivity.

- Returns masked key preview, model count, and the live tier and quota from the `X-AA-Tier` and `X-RateLimit-*` headers
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
        "args": ["aa-mcp"],
        "env": {
          "ARTIFICIAL_ANALYSIS_API_KEY": "aa_your_key_here"
        }
      }
    }
  }
}
```

For MCP client examples, see
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

For development, run the release checks from a source checkout:

```bash
uv sync --dev
uv run pytest
uv run ruff check .
uv build
uv run twine check dist/*
```

## Known Limitations

- **Rate limit**: Free 100 / Pro 500 requests per fixed 24-hour window. The LLM list spans several pages (about 4 requests), so results are cached per process
- **Free fields only**: individual benchmarks (MMLU-Pro, GPQA, HLE, and so on), the Math Index, and media `appearances`/`release_date` are Pro-only. The Coding Index is always null upstream
- **No explicit "updated_at" field**: Update detection relies on snapshot diffs, not API metadata
- **LLM data only for snapshots**: Media model snapshot tracking is not yet implemented
- **CritPt completeness**: The upstream evaluation API requires submissions for the full public problem set; this server validates object shape but cannot verify set completeness locally
- **Snapshot series**: V2 snapshots are saved as `llm_models_v2_*` because V2 speed figures use a different benchmark prompt than the legacy routes; legacy `llm_models_*` files are not diffed
- **Snapshot storage**: Local filesystem only; no cloud sync

## Attribution

<p>
  <img src="https://raw.githubusercontent.com/Leev1s/aa-mcp/main/assets/artificial-analysis-logo.svg" alt="Artificial Analysis" width="260">
</p>

This project uses data and benchmark resources from
[Artificial Analysis](https://artificialanalysis.ai/).

Attribution is required for all use of the Artificial Analysis free API. If you
publish outputs, dashboards, reports, or derivative analysis using data returned
by this MCP server, include attribution to
[artificialanalysis.ai](https://artificialanalysis.ai/).

CritPt benchmark evaluation data should also include attribution to the
[CritPt project](https://critpt.com/).
