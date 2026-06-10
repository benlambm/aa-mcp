from __future__ import annotations

import httpx
import pytest

from aa_mcp.client import AAClient, AAConnectionError, AARequestError, _check_response


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


def test_get_retries_timeout_once_and_returns_data(monkeypatch) -> None:
    calls = 0

    class FlakyHTTPClient:
        def __init__(self, timeout: float) -> None:
            assert timeout == 1

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def get(self, url: str, headers: dict, params: dict | None):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise httpx.TimeoutException("read timed out")
            return httpx.Response(
                200,
                json={"data": [{"id": "model-1", "name": "Example"}]},
                request=httpx.Request("GET", url),
            )

    monkeypatch.setattr(httpx, "Client", FlakyHTTPClient)

    client = AAClient(api_key="test-key", timeout=1, max_retries=1)
    models = client.get_llm_models()

    assert calls == 2
    assert models == [{"id": "model-1", "name": "Example"}]


def test_get_retries_transient_http_status_once(monkeypatch) -> None:
    calls = 0

    class FlakyHTTPClient:
        def __init__(self, timeout: float) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def get(self, url: str, headers: dict, params: dict | None):
            nonlocal calls
            calls += 1
            if calls == 1:
                return httpx.Response(
                    503,
                    json={"error": "busy"},
                    request=httpx.Request("GET", url),
                )
            return httpx.Response(
                200,
                json={"data": [{"id": "model-1"}]},
                request=httpx.Request("GET", url),
            )

    monkeypatch.setattr(httpx, "Client", FlakyHTTPClient)

    client = AAClient(api_key="test-key", timeout=1, max_retries=1)

    assert client.get_llm_models() == [{"id": "model-1"}]
    assert calls == 2


def test_post_uses_longer_default_timeout_than_get(monkeypatch) -> None:
    observed: list[float] = []

    class RecordingHTTPClient:
        def __init__(self, timeout: float) -> None:
            observed.append(timeout)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def post(self, url: str, headers: dict, json: dict):
            return httpx.Response(
                200,
                json={"accuracy": 1.0},
                request=httpx.Request("POST", url),
            )

    monkeypatch.setattr(httpx, "Client", RecordingHTTPClient)

    client = AAClient(api_key="test-key", timeout=8, post_timeout=120)
    client.evaluate_critpt([{"problem_id": "p"}])

    assert observed == [120]


def test_post_timeout_is_not_retried(monkeypatch) -> None:
    calls = 0

    class TimeoutHTTPClient:
        def __init__(self, timeout: float) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def post(self, url: str, headers: dict, json: dict):
            nonlocal calls
            calls += 1
            raise httpx.TimeoutException("read timed out")

    monkeypatch.setattr(httpx, "Client", TimeoutHTTPClient)

    client = AAClient(api_key="test-key", timeout=1, max_retries=3)

    with pytest.raises(AAConnectionError):
        client.evaluate_critpt([{"problem_id": "p"}])
    assert calls == 1


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
