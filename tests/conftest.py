"""Shared pytest fixtures.

Puts the ``src/`` layout on ``sys.path`` and provides a temp config store +
a known-good settings dict so individual tests stay short and focused.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

import pytest

# Make ``src/`` importable without requiring an install. Resolves the repo root
# from this file's location so it works regardless of pytest's cwd.
_REPO_ROOT = Path(__file__).resolve().parents[1]
_SRC_DIR = _REPO_ROOT / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from profile_settings import ProfileStore  # noqa: E402


@pytest.fixture
def valid_settings_dict() -> dict[str, Any]:
    """A dict that passes every validator — the happy-path baseline."""
    return {
        "username": "sohaib123",
        "email": "sohaib@example.com",
        "password": "Str0ng!Pass",
        "theme": "light",
    }


@pytest.fixture
def temp_store(tmp_path: Path) -> ProfileStore:
    """A ``ProfileStore`` backed by a config.json in a throwaway tmp_path."""
    return ProfileStore(tmp_path / "config.json")
