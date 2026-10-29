from __future__ import annotations

import httpx
import pytest

from aa_mcp.client import (
    AAClient,
    AAConnectionError,
    AARateLimitError,
    AARequestError,
    _check_response,
)


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


class RoutedHTTPClient:
    """Fake httpx.Client that serves canned V2 bodies by (path, page)."""

    def __init__(self, routes: dict, headers: dict | None = None) -> None:
        self.routes = routes
        self.headers = headers or {}
        self.requests: list[tuple[str, dict | None]] = []

    def __call__(self, timeout: float):
        return self

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def get(self, url: str, headers: dict, params: dict | None):
        path = url.removeprefix("https://artificialanalysis.ai/api/v2")
        self.requests.append((path, params))
        page = (params or {}).get("page", 1)
        return httpx.Response(
            200,
            json=self.routes[(path, page)],
            headers=self.headers,
            request=httpx.Request("GET", url),
        )


def _v2_llm(model_id: str, price_in=None, price_out=None, tps=None) -> dict:
    return {
        "id": model_id,
        "name": model_id,
        "slug": model_id,
        "model_creator": {"id": "c1", "name": "Example Co"},
        "evaluations": {"artificial_analysis_intelligence_index": 50.0},
        "pricing": {"price_1m_input_tokens": price_in, "price_1m_output_tokens": price_out},
        "performance": {
            "median_output_tokens_per_second": tps,
            "median_time_to_first_token_seconds": 1.5,
            "median_time_to_first_answer_token_seconds": 2.5,
            "median_end_to_end_response_time_seconds": 9.0,
        },
    }


def test_get_llm_models_walks_free_pages_and_restores_legacy_fields(monkeypatch) -> None:
    path = "/language/models/free"
    fake = RoutedHTTPClient(
        {
            (path, 1): {
                "tier": "free",
                "pagination": {"page": 1, "page_size": 1, "total_pages": 2, "has_more": True},
                "data": [_v2_llm("m1", price_in=4, price_out=20, tps=88.0)],
            },
            (path, 2): {
                "tier": "free",
                "pagination": {"page": 2, "page_size": 1, "total_pages": 2, "has_more": False},
                "data": [_v2_llm("m2")],
            },
        }
    )
    monkeypatch.setattr(httpx, "Client", fake)

    models = AAClient(api_key="test-key").get_llm_models()

    assert fake.requests == [(path, None), (path, {"page": 2})]
    assert [m["id"] for m in models] == ["m1", "m2"]
    first, second = models
    assert first["pricing"]["price_1m_blended_3_to_1"] == 8
    assert first["median_output_tokens_per_second"] == 88.0
    assert first["median_time_to_first_token_seconds"] == 1.5
    assert first["median_time_to_first_answer_token"] == 2.5
    assert first["performance"]["median_end_to_end_response_time_seconds"] == 9.0
    # No measured prices means no blended price, never a fake zero.
    assert "price_1m_blended_3_to_1" not in second["pricing"]
    assert second["median_output_tokens_per_second"] is None


def test_get_media_models_uses_free_route_and_restores_rank(monkeypatch) -> None:
    path = "/media/music/instrumental/models/free"
    fake = RoutedHTTPClient(
        {
            (path, 1): {
                "tier": "free",
                "data": [
                    {"id": "a", "elo": 1200, "ci_95": 9},
                    {"id": "b", "elo": 1100, "ci_95": 12},
                ],
            }
        }
    )
    monkeypatch.setattr(httpx, "Client", fake)

    models = AAClient(api_key="test-key").get_media_models("music-instrumental")

    assert fake.requests == [(path, None)]
    assert [(m["id"], m["rank"]) for m in models] == [("a", 1), ("b", 2)]


def test_list_results_are_cached_until_ttl_expires(monkeypatch) -> None:
    path = "/language/models/free"
    fake = RoutedHTTPClient({(path, 1): {"tier": "free", "data": [_v2_llm("m1")]}})
    monkeypatch.setattr(httpx, "Client", fake)

    AAClient(api_key="test-key").get_llm_models()
    AAClient(api_key="test-key").get_llm_models()
    assert len(fake.requests) == 1

    AAClient(api_key="test-key", cache_seconds=0).get_llm_models()
    assert len(fake.requests) == 2


def test_healthcheck_bypasses_cache_and_reports_rate_limit(monkeypatch) -> None:
    path = "/language/models/free"
    fake = RoutedHTTPClient(
        {(path, 1): {"tier": "free", "data": [_v2_llm("m1"), _v2_llm("m2")]}},
        headers={
            "X-AA-Tier": "free",
            "X-RateLimit-Limit": "100",
            "X-RateLimit-Remaining": "97",
            "X-RateLimit-Reset": "1793380397",
        },
    )
    monkeypatch.setattr(httpx, "Client", fake)

    client = AAClient(api_key="test-key")
    client.get_llm_models()
    result = client.healthcheck()

    assert len(fake.requests) == 2
    assert result == {
        "ok": True,
        "model_count": 2,
        "rate_limit": {
            "tier": "free",
            "limit": "100",
            "remaining": "97",
            "reset": "1793380397",
        },
    }


def test_check_response_reports_quota_from_headers_on_429() -> None:
    response = httpx.Response(
        429,
        json={"error": "Rate limit exceeded"},
        headers={"Retry-After": "3600", "X-RateLimit-Limit": "100"},
        request=httpx.Request("GET", "https://artificialanalysis.ai/api/v2/x"),
    )

    with pytest.raises(AARateLimitError) as exc:
        _check_response(response)

    assert "100 requests per 24-hour window" in str(exc.value)
    assert "3600" in str(exc.value)


def test_check_response_explains_tier_403() -> None:
    response = httpx.Response(
        403,
        json={"error": "Language models list requires a Pro subscription"},
        request=httpx.Request("GET", "https://artificialanalysis.ai/api/v2/x"),
    )

    with pytest.raises(AARequestError) as exc:
        _check_response(response)

    assert exc.value.status_code == 403
    assert "requires a Pro subscription" in str(exc.value)
