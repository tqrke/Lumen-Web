"""LUMEN theme system — clean, Edge-inspired luxury palette."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from core.paths import THEMES

# Edge dark + subtle jazz warmth (muted gold accent, no neon)
DEFAULT = {
    "name": "Edge Jazz",
    "bg0": "#1b1b1b",
    "bg1": "#242424",
    "bg2": "#2d2d2d",
    "bg3": "#383838",
    "border": "#3a3a3a",
    "primary": "#0078D4",
    "accent": "#0078D4",
    "jazz": "#b8956a",
    "success": "#5ea86a",
    "text": "#f0f0f0",
    "text_muted": "#9a9a9a",
    "vpn_bg": "#242424",
    "vpn_text": "#9a9a9a",
    "titlebar": "#1b1b1b",
    "tab_active": "#1b1b1b",
    "tab_inactive": "#2d2d2d",
    "omnibox": "#2d2d2d",
}


def list_themes() -> list[str]:
    names = ["edge-jazz"]
    if THEMES.exists():
        for f in sorted(THEMES.glob("*.json")):
            names.append(f.stem)
    return list(dict.fromkeys(names))


def load_theme(name: str) -> dict:
    base = deepcopy(DEFAULT)
    if name in ("edge-jazz", "midnight"):
        return base
    path = THEMES / f"{name}.json"
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            base.update(data)
            base["name"] = data.get("name", name)
        except (json.JSONDecodeError, OSError):
            pass
    return base


def global_stylesheet(c: dict) -> str:
    jazz = c.get("jazz", c["primary"])
    return f"""
    * {{
        font-family: "Segoe UI Variable Text", "Segoe UI", system-ui, sans-serif;
        font-size: 13px;
    }}
    QMainWindow {{ background: {c['bg0']}; }}
    QStatusBar {{
        background: {c['bg1']};
        color: {c['text_muted']};
        border-top: 1px solid {c['border']};
        font-size: 11px;
        padding: 0 12px;
        min-height: 22px;
    }}
    QTabBar {{
        background: {c['bg1']};
        qproperty-drawBase: 0;
    }}
    QTabBar::tab {{
        background: {c['tab_inactive']};
        color: {c['text_muted']};
        padding: 8px 16px;
        min-width: 80px;
        max-width: 200px;
        border: none;
        border-top-left-radius: 6px;
        border-top-right-radius: 6px;
        margin: 4px 2px 0 2px;
        font-size: 12px;
    }}
    QTabBar::tab:selected {{
        background: {c['tab_active']};
        color: {c['text']};
        border-bottom: 2px solid {jazz};
    }}
    QTabBar::tab:hover:!selected {{
        background: {c['bg2']};
        color: {c['text']};
    }}
    QTabBar::close-button {{
        subcontrol-position: right;
        border-radius: 3px;
        margin: 2px;
    }}
    QTabBar::close-button:hover {{
        background: {c['bg3']};
    }}
    QToolTip {{
        background: {c['bg2']};
        color: {c['text']};
        border: 1px solid {c['border']};
        padding: 6px 10px;
        border-radius: 4px;
        font-size: 12px;
    }}
    QScrollBar:vertical {{ background: transparent; width: 8px; }}
    QScrollBar::handle:vertical {{
        background: {c['bg3']}; border-radius: 4px; min-height: 24px;
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    QMenu {{
        background: {c['bg2']};
        color: {c['text']};
        border: 1px solid {c['border']};
        border-radius: 8px;
        padding: 6px 4px;
        font-size: 12px;
    }}
    QMenu::item {{
        padding: 8px 28px 8px 16px;
        border-radius: 4px;
        margin: 2px 4px;
    }}
    QMenu::item:selected {{
        background: {c['bg3']};
        color: {c['text']};
    }}
    QMenu::separator {{
        height: 1px;
        background: {c['border']};
        margin: 4px 8px;
    }}
    """
