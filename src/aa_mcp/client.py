"""Artificial Analysis API client."""

from __future__ import annotations

import os
import time
from typing import Any

import httpx

AA_BASE_URL = "https://artificialanalysis.ai/api/v2"
DEFAULT_TIMEOUT_SECONDS = 8.0
DEFAULT_MAX_RETRIES = 2
DEFAULT_CACHE_SECONDS = 3600.0
MAX_PAGES = 50
TRANSIENT_GET_STATUS_CODES = {502, 503, 504}

RATE_LIMIT_HEADERS = {
    "tier": "X-AA-Tier",
    "limit": "X-RateLimit-Limit",
    "remaining": "X-RateLimit-Remaining",
    "reset": "X-RateLimit-Reset",
}

# Legacy top-level speed fields -> their names under V2 `performance`
LLM_PERFORMANCE_FIELDS = {
    "median_output_tokens_per_second": "median_output_tokens_per_second",
    "median_time_to_first_token_seconds": "median_time_to_first_token_seconds",
    "median_time_to_first_answer_token": "median_time_to_first_answer_token_seconds",
}

# Free quota is 100 requests per 24-hour window and the LLM list spans several
# pages, so list results are cached per process (AA_MCP_CACHE_SECONDS=0 disables).
_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}


def clear_cache() -> None:
    _cache.clear()


class AAError(Exception):
    """Base error for AA API operations."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class AAAuthError(AAError):
    """Authentication error (401)."""


class AARateLimitError(AAError):
    """Rate limit exceeded (429)."""


class AAServerError(AAError):
    """Upstream server error (5xx)."""


class AAConnectionError(AAError):
    """Transient network or upstream availability failure."""


class AARequestError(AAError):
    """Invalid request or unsupported upstream response."""


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return max(0, int(raw))
    except ValueError:
        return default


def _get_api_key() -> str:
    key = os.environ.get("ARTIFICIAL_ANALYSIS_API_KEY", "").strip()
    if not key:
        raise AAAuthError(
            "ARTIFICIAL_ANALYSIS_API_KEY environment variable is not set. "
            "Get your key at https://artificialanalysis.ai/account"
        )
    return key


def _headers(api_key: str) -> dict[str, str]:
    return {
        "x-api-key": api_key,
        "Accept": "application/json",
    }


def _flatten_llm(model: dict[str, Any]) -> dict[str, Any]:
    """Add the legacy flat fields the tools expect to a V2 language model record."""
    out = dict(model)
    performance = model.get("performance")
    if isinstance(performance, dict):
        for legacy, current in LLM_PERFORMANCE_FIELDS.items():
            out.setdefault(legacy, performance.get(current))
    pricing = model.get("pricing")
    if isinstance(pricing, dict) and pricing.get("price_1m_blended_3_to_1") is None:
        price_in = pricing.get("price_1m_input_tokens")
        price_out = pricing.get("price_1m_output_tokens")
        if price_in is not None and price_out is not None:
            # AA's blended price weights input 3:1 against output
            out["pricing"] = {
                **pricing,
                "price_1m_blended_3_to_1": round((3 * price_in + price_out) / 4, 4),
            }
    return out


def _with_rank(models: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Restore legacy `rank`; V2 arena lists arrive already in leaderboard order."""
    return [
        {**m, "rank": i} if "elo" in m and "rank" not in m else m
        for i, m in enumerate(models, start=1)
    ]


def _check_response(resp: httpx.Response) -> None:
    def _response_message(default: str) -> str:
        try:
            body = resp.json()
        except ValueError:
            body = resp.text
        if isinstance(body, dict):
            detail = body.get("error") or body.get("message") or body
        else:
            detail = body.strip()[:500]
        return f"{default}: {detail}" if detail else default

    if resp.status_code == 401:
        raise AAAuthError(
            "Invalid or missing API key. Check ARTIFICIAL_ANALYSIS_API_KEY.", 401
        )
    if resp.status_code == 429:
        retry = resp.headers.get("Retry-After", "unknown")
        limit = resp.headers.get("X-RateLimit-Limit")
        quota = (
            f"{limit} requests per 24-hour window"
            if limit
            else "Free 100 / Pro 500 requests per 24-hour window"
        )
        raise AARateLimitError(
            f"Rate limit exceeded. Retry-After: {retry}s. Quota: {quota}.",
            429,
        )
    if resp.status_code == 403:
        raise AARequestError(
            _response_message(
                "Access denied (HTTP 403). The API key's tier or approvals "
                "do not cover this endpoint"
            ),
            403,
        )
    if resp.status_code >= 500:
        raise AAServerError(
            _response_message(
                f"Artificial Analysis server error (HTTP {resp.status_code}). "
                "Try again later."
            ),
            resp.status_code,
        )
    if resp.status_code >= 400:
        raise AARequestError(
            _response_message(f"Artificial Analysis request failed (HTTP {resp.status_code})"),
            resp.status_code,
        )
    resp.raise_for_status()


class AAClient:
    """Synchronous client for the Artificial Analysis free API."""

    def __init__(
        self,
        api_key: str | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
        cache_seconds: float | None = None,
    ):
        self.api_key = api_key or _get_api_key()
        self.timeout = (
            timeout
            if timeout is not None
            else _env_float("AA_MCP_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS)
        )
        self.max_retries = (
            max(0, max_retries)
            if max_retries is not None
            else _env_int("AA_MCP_MAX_RETRIES", DEFAULT_MAX_RETRIES)
        )
        self.cache_seconds = (
            cache_seconds
            if cache_seconds is not None
            else _env_float("AA_MCP_CACHE_SECONDS", DEFAULT_CACHE_SECONDS)
        )
        self.rate_limit: dict[str, str] = {}

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"{AA_BASE_URL}{path}"
        attempts = self.max_retries + 1
        for attempt in range(attempts):
            try:
                with httpx.Client(timeout=self.timeout) as client:
                    resp = client.get(url, headers=_headers(self.api_key), params=params)
            except httpx.TimeoutException as exc:
                if attempt < self.max_retries:
                    continue
                raise AAConnectionError(
                    f"Artificial Analysis request timed out after {attempts} attempts."
                ) from exc
            except httpx.TransportError as exc:
                if attempt < self.max_retries:
                    continue
                raise AAConnectionError(
                    "Artificial Analysis connection failed after "
                    f"{attempts} attempts: {exc}"
                ) from exc

            if resp.status_code in TRANSIENT_GET_STATUS_CODES:
                if attempt < self.max_retries:
                    continue
                raise AAConnectionError(
                    "Artificial Analysis temporarily unavailable "
                    f"(HTTP {resp.status_code}) after {attempts} attempts.",
                    resp.status_code,
                )

            self.rate_limit = {
                key: resp.headers[header]
                for key, header in RATE_LIMIT_HEADERS.items()
                if header in resp.headers
            }
            _check_response(resp)
            return resp.json()

        raise AAConnectionError("Artificial Analysis request failed unexpectedly.")

    def _get_all(self, path: str, use_cache: bool = True) -> list[dict[str, Any]]:
        """Fetch every page of a V2 list endpoint, served from cache while fresh."""
        cached = _cache.get(path)
        if use_cache and cached and time.monotonic() - cached[0] < self.cache_seconds:
            return list(cached[1])

        records: list[dict[str, Any]] = []
        for page in range(1, MAX_PAGES + 1):
            # Only paginated endpoints accept `page`; the first page needs none.
            body = self._get(path, {"page": page} if page > 1 else None)
            records.extend(body.get("data", []))
            if not (body.get("pagination") or {}).get("has_more"):
                break
        else:
            raise AARequestError(
                f"Artificial Analysis returned more than {MAX_PAGES} pages for {path}."
            )

        _cache[path] = (time.monotonic(), records)
        return list(records)

    def _post(self, path: str, json_body: dict[str, Any]) -> dict[str, Any]:
        url = f"{AA_BASE_URL}{path}"
        headers = _headers(self.api_key)
        headers["Content-Type"] = "application/json"
        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.post(url, headers=headers, json=json_body)
        except httpx.TimeoutException as exc:
            raise AAConnectionError(
                "Artificial Analysis request timed out. The request was not retried."
            ) from exc
        except httpx.TransportError as exc:
            raise AAConnectionError(
                f"Artificial Analysis connection failed: {exc}"
            ) from exc
        _check_response(resp)
        return resp.json()

    # ── LLM endpoints ──────────────────────────────────────────────

    LLM_MODELS_ENDPOINT = "/language/models/free"

    def get_llm_models(self, use_cache: bool = True) -> list[dict[str, Any]]:
        """Fetch all LLM models with evaluations, pricing, and speed data."""
        models = self._get_all(self.LLM_MODELS_ENDPOINT, use_cache)
        return [_flatten_llm(m) for m in models]

    # ── Media endpoints ─────────────────────────────────────────────

    MEDIA_ENDPOINTS = {
        "text-to-image": "/media/text-to-image/models/free",
        "image-editing": "/media/image-editing/models/free",
        "text-to-speech": "/media/text-to-speech/models/free",
        "text-to-video": "/media/text-to-video/models/free",
        "image-to-video": "/media/image-to-video/models/free",
        "text-to-video-audio": "/media/text-to-video-audio/models/free",
        "image-to-video-audio": "/media/image-to-video-audio/models/free",
        "speech-to-speech": "/media/speech-to-speech/models/free",
        "speech-to-text": "/media/speech-to-text/models/free",
        "music-instrumental": "/media/music/instrumental/models/free",
        "music-with-vocals": "/media/music/with-vocals/models/free",
    }

    def get_media_models(self, modality: str) -> list[dict[str, Any]]:
        """Fetch media model rankings for a given modality."""
        endpoint = self.MEDIA_ENDPOINTS.get(modality)
        if endpoint is None:
            valid = ", ".join(self.MEDIA_ENDPOINTS.keys())
            raise AAError(f"Unknown modality '{modality}'. Valid: {valid}")
        return _with_rank(self._get_all(endpoint))

    # ── CritPt endpoint ─────────────────────────────────────────────

    def evaluate_critpt(
        self,
        submissions: list[dict[str, Any]],
        batch_metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Submit a complete CritPt batch for official evaluation."""
        payload = {
            "submissions": submissions,
            "batch_metadata": batch_metadata or {},
        }
        return self._post("/critpt/evaluate", payload)

    # ── Healthcheck ─────────────────────────────────────────────────

    def healthcheck(self) -> dict[str, Any]:
        """Check connectivity + auth with a fresh, uncached fetch of LLM models."""
        models = self.get_llm_models(use_cache=False)
        return {
            "ok": True,
            "model_count": len(models),
            "rate_limit": dict(self.rate_limit),
        }
