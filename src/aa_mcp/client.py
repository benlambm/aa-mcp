"""Artificial Analysis API client."""

from __future__ import annotations

import os
from typing import Any

import httpx

AA_BASE_URL = "https://artificialanalysis.ai/api/v2"
DEFAULT_TIMEOUT_SECONDS = 8.0
DEFAULT_MAX_RETRIES = 2
TRANSIENT_GET_STATUS_CODES = {502, 503, 504}


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
        raise AARateLimitError(
            f"Rate limit exceeded. Retry-After: {retry}s. "
            f"Free API limit is 1000 requests/day.",
            429,
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

            _check_response(resp)
            return resp.json()

        raise AAConnectionError("Artificial Analysis request failed unexpectedly.")

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

    def get_llm_models(self) -> list[dict[str, Any]]:
        """Fetch all LLM models with evaluations, pricing, and speed data."""
        data = self._get("/data/llms/models")
        return data.get("data", [])

    # ── Media endpoints ─────────────────────────────────────────────

    MEDIA_ENDPOINTS = {
        "text-to-image": "/data/media/text-to-image",
        "image-editing": "/data/media/image-editing",
        "text-to-speech": "/data/media/text-to-speech",
        "text-to-video": "/data/media/text-to-video",
        "image-to-video": "/data/media/image-to-video",
    }

    def get_media_models(
        self, modality: str, include_categories: bool = False
    ) -> list[dict[str, Any]]:
        """Fetch media model rankings for a given modality."""
        endpoint = self.MEDIA_ENDPOINTS.get(modality)
        if endpoint is None:
            valid = ", ".join(self.MEDIA_ENDPOINTS.keys())
            raise AAError(f"Unknown modality '{modality}'. Valid: {valid}")
        params = {}
        if include_categories:
            params["include_categories"] = "true"
        data = self._get(endpoint, params)
        return data.get("data", [])

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
        """Run a lightweight connectivity + auth check by fetching LLM models."""
        data = self._get("/data/llms/models")
        model_count = len(data.get("data", []))
        return {
            "ok": True,
            "model_count": model_count,
            "prompt_options": data.get("prompt_options", {}),
        }
