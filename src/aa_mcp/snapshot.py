"""Snapshot engine: save, load, and diff model data for update tracking."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Fields we track for changes in LLM models (noise-resistant)
LLM_TRACKED_FIELDS = {
    "name",
    "slug",
    "model_creator",
    "median_output_tokens_per_second",
    "median_time_to_first_token_seconds",
}

# Evaluation sub-fields to track
LLM_EVAL_FIELDS = {
    "artificial_analysis_intelligence_index",
    "artificial_analysis_coding_index",
    "artificial_analysis_math_index",
    "mmlu_pro",
    "gpqa",
    "hle",
    "livecodebench",
    "math_500",
    "aime",
}

# Pricing sub-fields to track
LLM_PRICING_FIELDS = {
    "price_1m_blended_3_to_1",
    "price_1m_input_tokens",
    "price_1m_output_tokens",
}

# Threshold for float changes (ignore noise below this)
FLOAT_CHANGE_THRESHOLD = 0.01

# Media tracked fields
MEDIA_TRACKED_FIELDS = {
    "name",
    "slug",
    "model_creator",
    "elo",
    "rank",
    "release_date",
}


def _default_snapshot_dir() -> Path:
    base = os.environ.get(
        "AA_MCP_SNAPSHOT_DIR",
        os.path.join(os.path.expanduser("~"), ".local", "share", "aa-mcp", "snapshots"),
    )
    p = Path(base)
    p.mkdir(parents=True, exist_ok=True)
    return p


def _normalize_model(model: dict[str, Any], kind: str = "llm") -> dict[str, Any]:
    """Extract only tracked fields from a model for snapshot storage."""
    if kind == "llm":
        out: dict[str, Any] = {"id": model.get("id")}
        for f in LLM_TRACKED_FIELDS:
            if f in model:
                out[f] = model[f]
        # Flatten evaluations
        evals = model.get("evaluations", {})
        out["evaluations"] = {}
        for f in LLM_EVAL_FIELDS:
            if f in evals:
                out["evaluations"][f] = evals[f]
        # Flatten pricing
        pricing = model.get("pricing", {})
        out["pricing"] = {}
        for f in LLM_PRICING_FIELDS:
            if f in pricing:
                out["pricing"][f] = pricing[f]
        return out
    else:
        out = {"id": model.get("id")}
        for f in MEDIA_TRACKED_FIELDS:
            if f in model:
                out[f] = model[f]
        return out


def _normalize_models(
    models: list[dict[str, Any]], kind: str = "llm"
) -> dict[str, dict[str, Any]]:
    """Build id -> normalized_model mapping."""
    return {m["id"]: _normalize_model(m, kind) for m in models if m.get("id")}


def save_snapshot(
    data: dict[str, Any],
    name: str,
    snapshot_dir: Path | None = None,
) -> Path:
    """Save a snapshot to disk. Returns the file path."""
    d = snapshot_dir or _default_snapshot_dir()
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = d / f"{name}_{ts}.json"
    path.write_text(json.dumps(data, indent=2, default=str))
    return path


def load_latest_snapshot(
    name: str, snapshot_dir: Path | None = None
) -> dict[str, Any] | None:
    """Load the most recent snapshot for a given name, or None if none exists."""
    d = snapshot_dir or _default_snapshot_dir()
    pattern = f"{name}_*.json"
    files = sorted(d.glob(pattern), reverse=True)
    if not files:
        return None
    return json.loads(files[0].read_text())


def _float_changed(a: Any, b: Any) -> bool:
    """Check if two values changed meaningfully (threshold for floats)."""
    if a is None and b is None:
        return False
    if a is None or b is None:
        return True
    try:
        fa, fb = float(a), float(b)
        return abs(fa - fb) > FLOAT_CHANGE_THRESHOLD
    except (TypeError, ValueError):
        return a != b


def _diff_value(old: Any, new: Any, field_path: str) -> dict[str, Any] | None:
    """Return a change descriptor if value changed meaningfully."""
    if isinstance(old, dict) and isinstance(new, dict):
        changes = []
        all_keys = set(old.keys()) | set(new.keys())
        for k in sorted(all_keys):
            sub = _diff_value(old.get(k), new.get(k), f"{field_path}.{k}")
            if sub:
                changes.append(sub)
        if not changes:
            return None
        return {"field": field_path, "type": "nested", "changes": changes}
    if _float_changed(old, new):
        return {
            "field": field_path,
            "old": old,
            "new": new,
        }
    return None


def diff_snapshots(
    old: dict[str, dict[str, Any]],
    new: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """
    Compare two normalized snapshot maps (id -> model).
    Returns structured diff with added, removed, and changed models.
    """
    old_ids = set(old.keys())
    new_ids = set(new.keys())

    added_ids = new_ids - old_ids
    removed_ids = old_ids - new_ids
    common_ids = old_ids & new_ids

    added = [new[mid] for mid in sorted(added_ids)]
    removed = [old[mid] for mid in sorted(removed_ids)]

    changed: list[dict[str, Any]] = []
    for mid in sorted(common_ids):
        old_m = old[mid]
        new_m = new[mid]
        field_changes: list[dict[str, Any]] = []

        # Check top-level fields
        all_keys = set(old_m.keys()) | set(new_m.keys())
        for key in sorted(all_keys):
            if key == "id":
                continue
            diff = _diff_value(old_m.get(key), new_m.get(key), key)
            if diff:
                field_changes.append(diff)

        if field_changes:
            changed.append(
                {
                    "id": mid,
                    "name": new_m.get("name", old_m.get("name", "")),
                    "changes": field_changes,
                }
            )

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "added": len(added),
            "removed": len(removed),
            "changed": len(changed),
            "total_old": len(old),
            "total_new": len(new),
        },
        "added": added,
        "removed": removed,
        "changed": changed,
    }


def format_diff_readable(diff: dict[str, Any]) -> str:
    """Format a diff dict into a human-readable summary string."""
    lines: list[str] = []
    s = diff["summary"]
    lines.append(f"Snapshot diff ({diff['timestamp']}):")
    lines.append(
        f"  Models: {s['total_old']} -> {s['total_new']}  "
        f"(+{s['added']} new, -{s['removed']} removed, ~{s['changed']} changed)"
    )

    if diff["added"]:
        lines.append("")
        lines.append("NEW MODELS:")
        for m in diff["added"]:
            creator = ""
            if isinstance(m.get("model_creator"), dict):
                creator = f" by {m['model_creator'].get('name', '?')}"
            lines.append(f"  + {m.get('name', m.get('id', '?'))}{creator}")

    if diff["removed"]:
        lines.append("")
        lines.append("REMOVED MODELS:")
        for m in diff["removed"]:
            lines.append(f"  - {m.get('name', m.get('id', '?'))}")

    if diff["changed"]:
        lines.append("")
        lines.append("CHANGED MODELS:")
        for c in diff["changed"]:
            lines.append(f"  ~ {c['name']} ({c['id']})")
            for ch in c["changes"]:
                if ch.get("type") == "nested":
                    for sub in ch.get("changes", []):
                        lines.append(
                            f"      {sub['field']}: {_fmt_val(sub.get('old'))} -> {_fmt_val(sub.get('new'))}"
                        )
                else:
                    lines.append(
                        f"    {ch['field']}: {_fmt_val(ch.get('old'))} -> {_fmt_val(ch.get('new'))}"
                    )

    return "\n".join(lines)


def _fmt_val(v: Any) -> str:
    if v is None:
        return "N/A"
    if isinstance(v, float):
        return f"{v:.4g}"
    return str(v)
