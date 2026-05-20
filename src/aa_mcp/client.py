"""Artificial Analysis API client."""

from __future__ import annotations

import os
from typing import Any

import httpx

AA_BASE_URL = "https://artificialanalysis.ai/api/v2"
DEFAULT_TIMEOUT = 30.0


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
            f"Artificial Analysis server error (HTTP {resp.status_code}). "
            f"Try again later.",
            resp.status_code,
        )
    resp.raise_for_status()


class AAClient:
    """Synchronous client for the Artificial Analysis free API."""

    def __init__(self, api_key: str | None = None, timeout: float = DEFAULT_TIMEOUT):
        self.api_key = api_key or _get_api_key()
        self.timeout = timeout

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"{AA_BASE_URL}{path}"
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.get(url, headers=_headers(self.api_key), params=params)
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
