from __future__ import annotations

import pytest

from aa_mcp.client import clear_cache


@pytest.fixture(autouse=True)
def _fresh_cache():
    clear_cache()
    yield
    clear_cache()
