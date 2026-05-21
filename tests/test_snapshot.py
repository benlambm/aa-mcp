from __future__ import annotations

from aa_mcp.snapshot import diff_snapshots


def test_diff_snapshots_ignores_small_float_noise() -> None:
    old = {
        "model-1": {
            "id": "model-1",
            "name": "Model 1",
            "evaluations": {"artificial_analysis_intelligence_index": 80.0},
        }
    }
    new = {
        "model-1": {
            "id": "model-1",
            "name": "Model 1",
            "evaluations": {"artificial_analysis_intelligence_index": 80.005},
        }
    }

    diff = diff_snapshots(old, new)

    assert diff["summary"]["changed"] == 0


def test_diff_snapshots_reports_added_removed_and_changed() -> None:
    old = {
        "old-model": {"id": "old-model", "name": "Old"},
        "changed-model": {"id": "changed-model", "name": "Before"},
    }
    new = {
        "new-model": {"id": "new-model", "name": "New"},
        "changed-model": {"id": "changed-model", "name": "After"},
    }

    diff = diff_snapshots(old, new)

    assert diff["summary"] == {
        "added": 1,
        "removed": 1,
        "changed": 1,
        "total_old": 2,
        "total_new": 2,
    }
    assert diff["added"][0]["id"] == "new-model"
    assert diff["removed"][0]["id"] == "old-model"
    assert diff["changed"][0]["id"] == "changed-model"
