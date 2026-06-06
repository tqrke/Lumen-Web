"""Resolve paths for dev and PyInstaller frozen EXE."""

from __future__ import annotations

import sys
from pathlib import Path


def app_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent.parent


def user_data() -> Path:
    p = Path.home() / ".lumen"
    p.mkdir(parents=True, exist_ok=True)
    return p


ROOT = app_root()
ASSETS = ROOT / "assets"
THEMES = ROOT / "themes"
FILTERS = ROOT / "filters"
SETTINGS_PATH = user_data() / "settings.json"
BOOKMARKS_PATH = user_data() / "bookmarks.json"
CACHE_PATH = user_data() / "cache"
WEB_CACHE_PATH = user_data() / "webcache"
STORAGE_PATH = user_data() / "storage"
