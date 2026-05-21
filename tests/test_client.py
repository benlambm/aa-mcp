from __future__ import annotations

import httpx
import pytest

from aa_mcp.client import AAClient, AARequestError, _check_response


class RecordingClient(AAClient):
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def _post(self, path: str, json_body: dict) -> dict:
        self.calls.append((path, json_body))
        return {"accuracy": 0.75}


def test_evaluate_critpt_posts_expected_payload() -> None:
    client = RecordingClient()
    submissions = [
        {
            "problem_id": "Challenge_1_main",
            "generated_code": "def solution(): return 42",
            "model": "example-model",
            "generation_config": {"temperature": 0},
        }
    ]

    result = client.evaluate_critpt(submissions, {"run_id": "local"})

    assert result == {"accuracy": 0.75}
    assert client.calls == [
        (
            "/critpt/evaluate",
            {"submissions": submissions, "batch_metadata": {"run_id": "local"}},
        )
    ]


def test_check_response_raises_structured_request_error() -> None:
    request = httpx.Request("POST", "https://artificialanalysis.ai/api/v2/critpt/evaluate")
    response = httpx.Response(
        400,
        json={"error": "Invalid request body"},
        request=request,
    )

    with pytest.raises(AARequestError) as exc:
        _check_response(response)

    assert exc.value.status_code == 400
    assert "Invalid request body" in str(exc.value)
