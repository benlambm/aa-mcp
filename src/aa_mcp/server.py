"""Artificial Analysis MCP Server - exposes AA API data as MCP tools."""

from __future__ import annotations

import json
import logging
import os
import sys
from typing import Any

from mcp.server.fastmcp import FastMCP

from .client import AAAuthError, AAError, AARateLimitError, AAServerError, AAClient
from .snapshot import (
    diff_snapshots,
    format_diff_readable,
    load_latest_snapshot,
    save_snapshot,
    _normalize_models,
)

log_level = os.environ.get("AA_MCP_LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, log_level, logging.INFO),
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("aa-mcp")

mcp = FastMCP(
    "Artificial Analysis",
    instructions=(
        "MCP server wrapping the Artificial Analysis API. "
        "Use aa_list_llms to browse LLM models, aa_get_model for details, "
        "aa_compare_models to compare, aa_recent_model_updates for change tracking, "
        "aa_list_media_models for multimodal rankings, and aa_healthcheck to verify connectivity."
    ),
)


def _get_client() -> AAClient:
    """Create an AA client from environment."""
    return AAClient()


def _err_response(tool: str, e: Exception) -> str:
    """Format an error as agent-friendly JSON string."""
    if isinstance(e, AAAuthError):
        return json.dumps(
            {
                "error": "authentication_failed",
                "message": str(e),
                "hint": "Set ARTIFICIAL_ANALYSIS_API_KEY env var. "
                "Get a key at https://artificialanalysis.ai/account",
            }
        )
    if isinstance(e, AARateLimitError):
        return json.dumps(
            {
                "error": "rate_limited",
                "message": str(e),
                "hint": "Free API allows 1000 requests/day. Wait and retry.",
                "status_code": e.status_code,
            }
        )
    if isinstance(e, AAServerError):
        return json.dumps(
            {
                "error": "server_error",
                "message": str(e),
                "status_code": e.status_code,
            }
        )
    if isinstance(e, AAError):
        return json.dumps({"error": "api_error", "message": str(e)})
    logger.exception(f"Unexpected error in {tool}")
    return json.dumps(
        {"error": "internal_error", "message": f"{type(e).__name__}: {e}"}
    )


def _model_summary(m: dict[str, Any]) -> dict[str, Any]:
    """Extract a concise summary from an LLM model record."""
    evals = m.get("evaluations", {})
    pricing = m.get("pricing", {})
    creator = m.get("model_creator", {})
    return {
        "id": m.get("id"),
        "name": m.get("name"),
        "slug": m.get("slug"),
        "creator": creator.get("name") if isinstance(creator, dict) else creator,
        "creator_id": creator.get("id") if isinstance(creator, dict) else None,
        "intelligence_index": evals.get("artificial_analysis_intelligence_index"),
        "coding_index": evals.get("artificial_analysis_coding_index"),
        "math_index": evals.get("artificial_analysis_math_index"),
        "price_blended_3to1": pricing.get("price_1m_blended_3_to_1"),
        "price_input": pricing.get("price_1m_input_tokens"),
        "price_output": pricing.get("price_1m_output_tokens"),
        "output_tps": m.get("median_output_tokens_per_second"),
        "ttft_seconds": m.get("median_time_to_first_token_seconds"),
    }


def _match_model(
    models: list[dict[str, Any]],
    identifier: str,
) -> list[dict[str, Any]]:
    """Find models matching an identifier (id, slug, or name substring)."""
    ident_lower = identifier.lower().strip()
    exact = [
        m
        for m in models
        if m.get("id") == identifier
        or (m.get("slug", "").lower() == ident_lower)
        or (m.get("name", "").lower() == ident_lower)
    ]
    if exact:
        return exact
    # Fuzzy: substring match on name or slug
    return [
        m
        for m in models
        if ident_lower in m.get("name", "").lower()
        or ident_lower in m.get("slug", "").lower()
    ]


# ── Tool 1: aa_list_llms ───────────────────────────────────────────


@mcp.tool()
def aa_list_llms(
    creator: str | None = None,
    name: str | None = None,
    slug: str | None = None,
    sort_by: str = "intelligence",
    limit: int = 20,
) -> str:
    """List LLM models from Artificial Analysis with optional filtering and sorting.

    Args:
        creator: Filter by creator name (case-insensitive substring match)
        name: Filter by model name (case-insensitive substring match)
        slug: Filter by slug (case-insensitive substring match)
        sort_by: Sort key - 'intelligence', 'price', 'speed', 'ttft', 'coding', 'math'
        limit: Max models to return (default 20)

    Returns:
        JSON array of model summaries.
    """
    try:
        client = _get_client()
        models = client.get_llm_models()

        # Apply filters
        if creator:
            c_lower = creator.lower()
            models = [
                m
                for m in models
                if c_lower
                in (
                    m.get("model_creator", {}).get("name", "")
                    if isinstance(m.get("model_creator"), dict)
                    else ""
                ).lower()
            ]
        if name:
            n_lower = name.lower()
            models = [m for m in models if n_lower in m.get("name", "").lower()]
        if slug:
            s_lower = slug.lower()
            models = [m for m in models if s_lower in m.get("slug", "").lower()]

        # Sort
        sort_keys = {
            "intelligence": lambda m: (
                m.get("evaluations", {}).get(
                    "artificial_analysis_intelligence_index", 0
                )
                or 0
            ),
            "price": lambda m: (
                m.get("pricing", {}).get("price_1m_blended_3_to_1", 999999) or 999999
            ),
            "speed": lambda m: -(m.get("median_output_tokens_per_second", 0) or 0),
            "ttft": lambda m: (m.get("median_time_to_first_token_seconds", 9999) or 9999),
            "coding": lambda m: (
                m.get("evaluations", {}).get("artificial_analysis_coding_index", 0)
                or 0
            ),
            "math": lambda m: (
                m.get("evaluations", {}).get("artificial_analysis_math_index", 0) or 0
            ),
        }
        reverse = True
        key_fn = sort_keys.get(sort_by, sort_keys["intelligence"])
        if sort_by == "price":
            reverse = False  # Cheapest first
        if sort_by == "ttft":
            reverse = False  # Fastest first
        models.sort(key=key_fn, reverse=reverse)

        results = [_model_summary(m) for m in models[:limit]]
        return json.dumps(
            {"count": len(results), "total_available": len(models), "models": results},
            indent=2,
        )
    except Exception as e:
        return _err_response("aa_list_llms", e)


# ── Tool 2: aa_get_model ───────────────────────────────────────────


@mcp.tool()
def aa_get_model(identifier: str) -> str:
    """Get detailed information about a single LLM model by id, slug, or name.

    Args:
        identifier: Model id (UUID), slug, or name. Partial matching supported.

    Returns:
        JSON object with full model details, or candidates if multiple matches.
    """
    try:
        client = _get_client()
        models = client.get_llm_models()
        matches = _match_model(models, identifier)

        if len(matches) == 0:
            return json.dumps(
                {
                    "error": "not_found",
                    "message": f"No model matching '{identifier}'.",
                    "hint": "Use aa_list_llms to browse available models.",
                }
            )
        if len(matches) == 1:
            m = matches[0]
            return json.dumps(
                {
                    "id": m.get("id"),
                    "name": m.get("name"),
                    "slug": m.get("slug"),
                    "model_creator": m.get("model_creator"),
                    "evaluations": m.get("evaluations", {}),
                    "pricing": m.get("pricing", {}),
                    "median_output_tokens_per_second": m.get(
                        "median_output_tokens_per_second"
                    ),
                    "median_time_to_first_token_seconds": m.get(
                        "median_time_to_first_token_seconds"
                    ),
                },
                indent=2,
            )

        # Multiple matches
        candidates = [
            {
                "id": m.get("id"),
                "name": m.get("name"),
                "slug": m.get("slug"),
                "creator": (
                    m.get("model_creator", {}).get("name", "")
                    if isinstance(m.get("model_creator"), dict)
                    else ""
                ),
            }
            for m in matches[:15]
        ]
        return json.dumps(
            {
                "error": "multiple_matches",
                "message": f"Found {len(matches)} models matching '{identifier}'.",
                "candidates": candidates,
                "hint": "Refine your query or use the exact id/slug.",
            },
            indent=2,
        )
    except Exception as e:
        return _err_response("aa_get_model", e)


# ── Tool 3: aa_compare_models ──────────────────────────────────────


@mcp.tool()
def aa_compare_models(identifiers: list[str]) -> str:
    """Compare multiple LLM models side by side on key metrics.

    Args:
        identifiers: List of model ids, slugs, or names (at least 2).

    Returns:
        JSON object with comparison table and per-model details.
    """
    try:
        if len(identifiers) < 2:
            return json.dumps(
                {
                    "error": "invalid_input",
                    "message": "Provide at least 2 model identifiers to compare.",
                }
            )

        client = _get_client()
        all_models = client.get_llm_models()

        resolved: list[dict[str, Any]] = []
        not_found: list[str] = []
        ambiguous: list[dict[str, Any]] = []

        for ident in identifiers:
            matches = _match_model(all_models, ident)
            if len(matches) == 0:
                not_found.append(ident)
            elif len(matches) == 1:
                resolved.append(matches[0])
            else:
                ambiguous.append(
                    {
                        "query": ident,
                        "candidates": [
                            {"id": m["id"], "name": m["name"]} for m in matches[:5]
                        ],
                    }
                )

        if not_found or ambiguous:
            return json.dumps(
                {
                    "error": "resolution_failed",
                    "not_found": not_found,
                    "ambiguous": ambiguous,
                    "resolved_count": len(resolved),
                    "hint": "Use exact ids or slugs. Use aa_list_llms to find them.",
                },
                indent=2,
            )

        # Build comparison
        comparison = []
        for m in resolved:
            evals = m.get("evaluations", {})
            pricing = m.get("pricing", {})
            creator = m.get("model_creator", {})
            comparison.append(
                {
                    "id": m.get("id"),
                    "name": m.get("name"),
                    "slug": m.get("slug"),
                    "creator": (
                        creator.get("name") if isinstance(creator, dict) else None
                    ),
                    "intelligence_index": evals.get(
                        "artificial_analysis_intelligence_index"
                    ),
                    "coding_index": evals.get("artificial_analysis_coding_index"),
                    "math_index": evals.get("artificial_analysis_math_index"),
                    "mmlu_pro": evals.get("mmlu_pro"),
                    "gpqa": evals.get("gpqa"),
                    "price_blended_3to1": pricing.get("price_1m_blended_3_to_1"),
                    "price_input": pricing.get("price_1m_input_tokens"),
                    "price_output": pricing.get("price_1m_output_tokens"),
                    "output_tps": m.get("median_output_tokens_per_second"),
                    "ttft_seconds": m.get("median_time_to_first_token_seconds"),
                }
            )

        # Compute rankings
        rankings: dict[str, list[str]] = {}
        for metric, key_fn in [
            ("intelligence", lambda c: c.get("intelligence_index") or 0),
            ("coding", lambda c: c.get("coding_index") or 0),
            ("math", lambda c: c.get("math_index") or 0),
            ("speed_output_tps", lambda c: c.get("output_tps") or 0),
            ("price_blended", lambda c: -(c.get("price_blended_3to1") or 999999)),
            ("ttft", lambda c: -(c.get("ttft_seconds") or 99999)),
        ]:
            ranked = sorted(comparison, key=key_fn, reverse=True)
            rankings[metric] = [c["name"] for c in ranked]

        return json.dumps(
            {
                "models": comparison,
                "rankings": rankings,
                "count": len(comparison),
            },
            indent=2,
        )
    except Exception as e:
        return _err_response("aa_compare_models", e)


# ── Tool 4: aa_recent_model_updates ────────────────────────────────


@mcp.tool()
def aa_recent_model_updates(save_new_snapshot: bool = True) -> str:
    """Detect recent LLM model changes by comparing current data to the last local snapshot.

    Identifies new models, removed models, and field-level changes (pricing, speed,
    intelligence scores, etc.). On first run, saves a baseline snapshot and reports
    the full model list as "initial baseline".

    Args:
        save_new_snapshot: If true (default), save the current data as the new snapshot
                          after diffing. Set false to preview-only.

    Returns:
        JSON with structured diff: added, removed, changed models with field-level deltas.
    """
    try:
        client = _get_client()
        current_models = client.get_llm_models()
        current_norm = _normalize_models(current_models, "llm")

        old_snapshot = load_latest_snapshot("llm_models")

        if old_snapshot is None:
            # First run: save baseline
            if save_new_snapshot:
                save_snapshot(current_norm, "llm_models")
            return json.dumps(
                {
                    "status": "baseline_created",
                    "message": "No previous snapshot found. Saved current data as baseline.",
                    "model_count": len(current_norm),
                    "hint": "Run again later to detect changes against this baseline.",
                    "models_sample": [
                        {"id": mid, "name": m.get("name", "")}
                        for mid, m in list(current_norm.items())[:10]
                    ],
                },
                indent=2,
            )

        old_norm = old_snapshot.get("models", old_snapshot)

        diff = diff_snapshots(old_norm, current_norm)

        if save_new_snapshot:
            save_snapshot(current_norm, "llm_models")

        readable = format_diff_readable(diff)

        # Check if nothing changed
        s = diff["summary"]
        if s["added"] == 0 and s["removed"] == 0 and s["changed"] == 0:
            return json.dumps(
                {
                    "status": "no_changes",
                    "message": "No model changes detected since last snapshot.",
                    "total_models": s["total_new"],
                    "readable": readable,
                },
                indent=2,
            )

        return json.dumps(
            {
                "status": "changes_detected",
                "readable": readable,
                "diff": diff,
            },
            indent=2,
        )
    except Exception as e:
        return _err_response("aa_recent_model_updates", e)


# ── Tool 5: aa_list_media_models ───────────────────────────────────


@mcp.tool()
def aa_list_media_models(
    modality: str = "text-to-image",
    top_n: int = 10,
    include_categories: bool = False,
) -> str:
    """List top-ranked multimodal / media models by Elo ratings.

    Args:
        modality: One of 'text-to-image', 'image-editing', 'text-to-speech',
                  'text-to-video', 'image-to-video'
        top_n: Number of top models to return (default 10)
        include_categories: Include per-category Elo breakdown (text-to-image, text-to-video only)

    Returns:
        JSON array of media model rankings.
    """
    try:
        client = _get_client()
        models = client.get_media_models(modality, include_categories)
        top = models[:top_n]
        return json.dumps(
            {
                "modality": modality,
                "count": len(top),
                "total_available": len(models),
                "models": top,
            },
            indent=2,
        )
    except Exception as e:
        return _err_response("aa_list_media_models", e)


# ── Tool 6: aa_healthcheck ─────────────────────────────────────────


@mcp.tool()
def aa_healthcheck() -> str:
    """Verify API key validity and upstream API reachability.

    Returns:
        JSON with connectivity status, model count, and any error details.
    """
    key = os.environ.get("ARTIFICIAL_ANALYSIS_API_KEY", "").strip()
    if not key:
        return json.dumps(
            {
                "ok": False,
                "error": "no_api_key",
                "message": "ARTIFICIAL_ANALYSIS_API_KEY is not set.",
                "hint": "Get a key at https://artificialanalysis.ai/account",
            }
        )

    masked = key[:4] + "..." + key[-4:] if len(key) > 8 else "***"
    try:
        client = AAClient(api_key=key)
        result = client.healthcheck()
        return json.dumps(
            {
                "ok": True,
                "api_key_preview": masked,
                "llm_model_count": result["model_count"],
                "prompt_options": result["prompt_options"],
                "rate_limit": "1000 requests/day (free tier)",
            },
            indent=2,
        )
    except AAAuthError as e:
        return json.dumps(
            {
                "ok": False,
                "api_key_preview": masked,
                "error": "auth_failed",
                "message": str(e),
            }
        )
    except AARateLimitError as e:
        return json.dumps(
            {
                "ok": False,
                "error": "rate_limited",
                "message": str(e),
            }
        )
    except Exception as e:
        return json.dumps(
            {
                "ok": False,
                "error": "connection_failed",
                "message": f"{type(e).__name__}: {e}",
            }
        )


# ── Entry point ────────────────────────────────────────────────────


def main():
    """Run the MCP server with stdio transport."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
