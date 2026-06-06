"""Deterministic everyday command router — high reliability for assistive use.

Matches canonical phrases BEFORE fuzzy STT interpretation to prevent
misheard commands like 'open you cheated' failing to open YouTube.
"""

from __future__ import annotations

import re

from ui.command_sanitize import expand_video_command, sanitize_command
from ui.grocery_control import GROCERY_STORES
from ui.intent_engine import (
    IntentResult,
    _match_grocery,
    _match_media_control,
    _match_scroll_control,
    _music_url,
    _weather_url,
    _web_search_url,
)
from ui.wake_words import normalize_command, strip_wake_text

_SITES: dict[str, tuple[str, str]] = {
    "youtube": ("YouTube", "https://www.youtube.com"),
    "google": ("Google", "https://www.google.com"),
    "gmail": ("Gmail", "https://mail.google.com"),
    "maps": ("Google Maps", "https://www.google.com/maps"),
    "github": ("GitHub", "https://github.com"),
    "wikipedia": ("Wikipedia", "https://wikipedia.org"),
    "reddit": ("Reddit", "https://www.reddit.com"),
    "netflix": ("Netflix", "https://www.netflix.com"),
    "amazon": ("Amazon", "https://www.amazon.com"),
    "spotify": ("Spotify", "https://open.spotify.com"),
    "outlook": ("Outlook", "https://outlook.live.com"),
    "facebook": ("Facebook", "https://www.facebook.com"),
    "instagram": ("Instagram", "https://www.instagram.com"),
    "twitter": ("X", "https://x.com"),
    "x": ("X", "https://x.com"),
    **{k: (k.title(), v) for k, v in GROCERY_STORES.items()},
}

_OPEN_RE = re.compile(
    r"^(?:open|go to|go|visit|launch|start|load|take me to|bring up|navigate to)\s+"
    r"(youtube|google|gmail|maps|github|wikipedia|reddit|netflix|amazon|spotify|"
    r"tesco|sainsburys|sainsbury|asda|morrisons|ocado|waitrose|iceland|aldi|"
    r"outlook|facebook|instagram|twitter|x)\s*$",
    re.I,
)

_SEARCH_RE = re.compile(
    r"^(?:search\s+the\s+web(?:\s+for)?|web search for|google|look up|find on (?:the )?web)\s+(.+)$",
    re.I,
)

_WEATHER_RE = re.compile(
    r"^(?:weather(?: in| for| at)?\s*(.+)|(?:what(?:'s| is) the weather(?: in| for)?)\s*(.+))$",
    re.I,
)


def _norm(text: str) -> str:
    t = strip_wake_text(text.strip())
    t = sanitize_command(normalize_command(t))
    t = expand_video_command(t)
    return t.lower().strip()


def is_fast_phrase(text: str) -> bool:
    """True when text matches a high-confidence everyday command."""
    return match_fast_command(text) is not None


def match_fast_command(text: str) -> IntentResult | None:
    """Return intent for well-known everyday commands, else None."""
    msg = _norm(text)
    if not msg:
        return None

    if msg in _SITES:
        name, url = _SITES[msg]
        return IntentResult(f"Opening {name}.", "navigate", url)

    if msg in ("youtube", "you tube", "u tube", "tube"):
        return IntentResult("Opening YouTube.", "navigate", _SITES["youtube"][1])

    m = _OPEN_RE.match(msg)
    if m:
        key = m.group(1).lower()
        if key in _SITES:
            name, url = _SITES[key]
            return IntentResult(f"Opening {name}.", "navigate", url)

    if msg in ("open settings", "show settings", "settings", "control center", "open control center"):
        return IntentResult("Opening settings.", "app", "settings")

    if msg in ("read page", "read this page", "read aloud", "read this", "read notifications", "what's on screen"):
        return IntentResult("Reading the page.", "app", "read_page")

    if msg in ("play music", "listen to music", "open music", "start music"):
        return IntentResult("Opening Spotify.", "navigate", "https://open.spotify.com")

    if re.match(r"^(go back|back|previous page)$", msg):
        return IntentResult("Going back.", "back")

    if re.match(r"^(new tab|open tab)$", msg):
        return IntentResult("Opening a new tab.", "new_tab")

    if re.match(r"^(reload|refresh)$", msg):
        return IntentResult("Refreshing.", "reload")

    if re.match(r"^(stop listening|go to sleep|sleep|goodbye lumen)$", msg):
        return IntentResult("Going to sleep. Say Lumen when you need me.", "app", "sleep")

    grocery = _match_grocery(msg)
    if grocery:
        return IntentResult(grocery[1], "grocery", grocery[0])

    m = _SEARCH_RE.match(msg)
    if m:
        q = m.group(1).strip()
        if q and len(q) > 1:
            return IntentResult(f"Searching the web for {q}.", "navigate", _web_search_url(q))

    m = _WEATHER_RE.match(msg)
    if m:
        place = (m.group(1) or m.group(2) or "today").strip() or "today"
        if place in ("today", "now", "here", "local"):
            place = "London"
        return IntentResult(f"Weather for {place}.", "navigate", _weather_url(place))

    if msg == "weather" or msg.startswith("weather "):
        place = msg.replace("weather", "", 1).strip() or "London"
        return IntentResult(f"Weather for {place}.", "navigate", _weather_url(place))

    if re.match(r"^set (?:a )?reminder(?: to)?\s+(.+)$", msg):
        task = re.sub(r"^set (?:a )?reminder(?: to)?\s+", "", msg, flags=re.I)
        return IntentResult(
            f"I'll note your reminder: {task}. Full calendar sync is coming soon.",
            "app",
            f"reminder:{task[:120]}",
        )

    scroll = _match_scroll_control(msg)
    if scroll:
        return IntentResult(scroll[1], "scroll", scroll[0])

    media = _match_media_control(msg)
    if media:
        return IntentResult(media[1], "media", media[0])

    music = re.match(r"^play (?:music )?(.+)$", msg)
    if music and "video" not in msg:
        q = music.group(1).strip()
        if re.match(
            r"^the (first|second|third|fourth|fifth|1st|2nd|3rd|4th|5th|one|two|three|four|five)$",
            q,
            re.I,
        ):
            media = _match_media_control(expand_video_command(f"play {q}"))
            if media:
                return IntentResult(media[1], "media", media[0])
        if q and q not in ("music", "a song", "something"):
            return IntentResult(f"Playing {q} on Spotify.", "navigate", _music_url(q))

    return None
