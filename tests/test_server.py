from __future__ import annotations

import json

import anyio

from aa_mcp import server


class FakeClient:
    def __init__(self) -> None:
        self.received = None

    def evaluate_critpt(self, submissions, batch_metadata=None):
        self.received = (submissions, batch_metadata)
        return {
            "accuracy": 0.5,
            "timeout_rate": 0.0,
            "server_timeout_count": 0,
            "judge_error_count": 0,
        }


def test_registered_mcp_tools_cover_public_surface() -> None:
    tools = anyio.run(server.mcp.list_tools)
    tool_names = {tool.name for tool in tools}

    assert tool_names == {
        "aa_list_llms",
        "aa_get_model",
        "aa_compare_models",
        "aa_list_recent_updates",
        "aa_list_media_models",
        "aa_evaluate_critpt",
        "aa_healthcheck",
    }


def test_aa_evaluate_critpt_validates_required_submission_fields() -> None:
    result = json.loads(server.aa_evaluate_critpt([{"problem_id": "Challenge_1_main"}]))

    assert result["error"] == "invalid_input"
    assert result["required_fields"] == [
        "generated_code",
        "generation_config",
        "model",
        "problem_id",
    ]
    assert result["invalid_submissions"] == [
        {
            "index": 0,
            "missing": ["generated_code", "generation_config", "model"],
        }
    ]


def test_aa_evaluate_critpt_returns_upstream_result(monkeypatch) -> None:
    fake = FakeClient()
    monkeypatch.setattr(server, "_get_client", lambda: fake)
    submissions = [
        {
            "problem_id": "Challenge_1_main",
            "generated_code": "def solution(): return 42",
            "model": "example-model",
            "generation_config": {"temperature": 0},
        }
    ]

    result = json.loads(server.aa_evaluate_critpt(submissions, {"run_id": "local"}))

    assert result["accuracy"] == 0.5
    assert fake.received == (submissions, {"run_id": "local"})
