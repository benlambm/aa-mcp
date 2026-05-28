from __future__ import annotations

import json

import anyio
import httpx

from aa_mcp.client import AAClient
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


def test_aa_list_llms_maps_repeated_timeout_to_connection_failed(monkeypatch) -> None:
    calls = 0

    class TimeoutHTTPClient:
        def __init__(self, timeout: float) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def get(self, url: str, headers: dict, params: dict | None):
            nonlocal calls
            calls += 1
            raise httpx.TimeoutException("read timed out")

    monkeypatch.setattr(httpx, "Client", TimeoutHTTPClient)
    monkeypatch.setattr(
        server,
        "_get_client",
        lambda: AAClient(api_key="test-key", timeout=1, max_retries=1),
    )

    result = json.loads(server.aa_list_llms(limit=5))

    assert calls == 2
    assert result["error"] == "connection_failed"
    assert "timed out" in result["message"]


def test_aa_list_llms_preserves_success_shape(monkeypatch) -> None:
    class FakeListClient:
        def get_llm_models(self):
            return [
                {
                    "id": "model-1",
                    "name": "Example 1",
                    "slug": "example-1",
                    "model_creator": {"id": "creator-1", "name": "Example Co"},
                    "evaluations": {
                        "artificial_analysis_intelligence_index": 80.5,
                        "artificial_analysis_coding_index": 70.0,
                    },
                    "pricing": {
                        "price_1m_blended_3_to_1": 1.25,
                    },
                    "median_output_tokens_per_second": 100,
                    "median_time_to_first_token_seconds": 0.5,
                }
            ]

    monkeypatch.setattr(server, "_get_client", lambda: FakeListClient())

    result = json.loads(server.aa_list_llms(limit=1))

    assert result["count"] == 1
    assert result["total_available"] == 1
    assert result["models"] == [
        {
            "id": "model-1",
            "name": "Example 1",
            "slug": "example-1",
            "model_creator": "Example Co",
            "model_creator_id": "creator-1",
            "artificial_analysis_intelligence_index": 80.5,
            "artificial_analysis_coding_index": 70.0,
            "artificial_analysis_math_index": None,
            "price_1m_blended_3_to_1": 1.25,
            "price_1m_input_tokens": None,
            "price_1m_output_tokens": None,
            "median_output_tokens_per_second": 100,
            "median_time_to_first_token_seconds": 0.5,
            "release_date": None,
        }
    ]
