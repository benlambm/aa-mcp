from __future__ import annotations

import importlib.machinery
import importlib.util
from pathlib import Path

import pytest


def load_installed_helper(name: str):
    path = Path.home() / ".local" / "bin" / name
    if not path.exists():
        pytest.skip(f"{path} is not installed")
    loader = importlib.machinery.SourceFileLoader(name.replace("-", "_"), str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


@pytest.mark.parametrize("name", ["aa-top20", "aa-update-check"])
def test_helper_parser_rejects_mcp_error_payload(name: str) -> None:
    helper = load_installed_helper(name)

    with pytest.raises(RuntimeError, match="tool error internal_error"):
        helper.parse_tool_text_payload(
            '{"error": "internal_error", "message": "read timed out"}'
        )
