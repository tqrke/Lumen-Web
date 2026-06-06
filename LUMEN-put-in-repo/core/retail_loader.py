"""Load UK grocery sites — Akamai blocks embedded Qt WebEngine unless we retry smartly."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from core.browser_identity import (
    apply_browser_identity,
    apply_retail_user_agent,
    clear_retail_headers,
    set_retail_referer,
)

log = logging.getLogger("lumen.retail")

AKAMAI_BLOCK_MARKERS = ("access denied", "edgesuite.net", "reference #")


@dataclass
class RetailLoadState:
    target_url: str
    store: str = ""
    attempt: int = 0
    max_attempts: int = 4
# view id -> state (attached on BrowserTab during retail load)
_PENDING: dict[int, RetailLoadState] = {}


def ensure_https(url: str) -> str:
    u = (url or "").strip()
    if u.startswith("http://"):
        return "https://" + u[7:]
    return u


def is_retail_grocery_url(url: str) -> bool:
    from ui.grocery_control import GROCERY_STORES, is_grocery_url

    u = ensure_https(url).lower()
    if is_grocery_url(u):
        return True
    return any(ensure_https(v).lower() in u or u in ensure_https(v).lower() for v in GROCERY_STORES.values())


def is_blocked_page(title: str, url: str) -> bool:
    t = (title or "").lower()
    u = (url or "").lower()
    if "access denied" in t:
        return True
    if any(m in u for m in AKAMAI_BLOCK_MARKERS):
        return True
    if "permission to access" in t and "tesco" in t:
        return True
    return False


def _store_from_url(url: str) -> str:
    low = url.lower()
    if "tesco" in low:
        return "tesco"
    if "sainsbury" in low:
        return "sainsburys"
    if "asda" in low:
        return "asda"
    if "morrisons" in low:
        return "morrisons"
    return ""


def _attempt_spec(state: RetailLoadState) -> tuple[str, str]:
    """Return (url, mode) for the current attempt."""
    url = ensure_https(state.target_url)
    store = state.store or _store_from_url(url)
    attempt = state.attempt

    if attempt == 0:
        return url, "desktop"
    if attempt == 1:
        return url, "mobile"
    if attempt == 2 and store == "tesco":
        return "https://www.tesco.com/", "mobile"
    if attempt == 3:
        set_retail_referer("https://www.google.co.uk/")
        return url, "desktop"
    return url, "fallback"


def begin_retail_load(view, profile, url: str, *, store: str = "") -> None:
    """Start a retail URL load with anti-Akamai retries."""
    from PyQt6.QtCore import QUrl

    state = RetailLoadState(target_url=ensure_https(url), store=store)
    _PENDING[id(view)] = state
    try:
        profile.clearHttpCache()
    except Exception:
        pass
    load_url, mode = _attempt_spec(state)
    _apply_mode(profile, mode)
    log.info("Retail load attempt %s mode=%s url=%s", state.attempt, mode, load_url)
    view.load(QUrl(load_url))


def on_retail_load_finished(view, profile, *, title: str, url: str) -> str | None:
    """
    Call from page loadFinished. Returns a user-facing status message, or None if still loading.
    """
    key = id(view)
    state = _PENDING.get(key)
    if not state:
        return None

    if not is_blocked_page(title, url):
        _PENDING.pop(key, None)
        clear_retail_headers()
        apply_browser_identity(profile)
        return None

    state.attempt += 1
    if state.attempt >= state.max_attempts:
        _PENDING.pop(key, None)
        clear_retail_headers()
        apply_browser_identity(profile)
        target = state.target_url
        opened = open_system_browser(target)
        return (
            f"Tesco blocked the built-in browser (Akamai). Opened in {opened} instead — "
            "say “add spaghetti” after you switch back here once groceries load in Edge."
        )

    load_url, mode = _attempt_spec(state)
    _apply_mode(profile, mode)
    from PyQt6.QtCore import QUrl

    log.info("Retail retry %s mode=%s url=%s", state.attempt, mode, load_url)
    view.load(QUrl(load_url))
    return f"Retrying Tesco (attempt {state.attempt + 1})…"


def _apply_mode(profile, mode: str) -> None:
    clear_retail_headers()
    if mode == "desktop":
        apply_browser_identity(profile)
    elif mode == "mobile":
        apply_retail_user_agent(profile, mobile=True)
    elif mode == "desktop_referer":
        apply_browser_identity(profile)
        set_retail_referer("https://www.google.co.uk/")
    elif mode == "fallback":
        apply_browser_identity(profile)


def open_system_browser(url: str) -> str:
    """Open URL in the user's real browser (Edge/Chrome) when WebEngine is blocked."""
    target = ensure_https(url)
    if sys.platform == "win32":
        for name in ("msedge", "chrome", "firefox"):
            path = shutil.which(name)
            if path:
                try:
                    subprocess.Popen([path, target], close_fds=True)
                    return name.title()
                except OSError as exc:
                    log.debug("Failed to launch %s: %s", name, exc)
        try:
            os.startfile(target)  # type: ignore[attr-defined]
            return "your browser"
        except OSError:
            pass
    try:
        import webbrowser
        webbrowser.open(target)
        return "your browser"
    except Exception:
        return "your browser"
