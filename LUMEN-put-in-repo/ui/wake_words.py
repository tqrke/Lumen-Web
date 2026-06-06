"""Wake word detection — accepts Vosk mishears of 'Lumen' without false triggers."""

from __future__ import annotations

import re

# Vosk / Google commonly mishear "Lumen" — especially British accents.
_WAKE_MISHEARS = frozenset({
    "lumen", "lumin", "human", "woman", "women", "lehman", "leman", "lewman",
    "looman", "loom", "loomin", "looming", "limon", "newman", "room", "luke",
    "lewmin", "louman", "loumen", "loomun", "lewmen", "luemen", "rumen",
})

_WAKE_PREFIXES = (
    "hey lumen", "hi lumen", "ok lumen", "a lumen", "loom in", "lu men", "lew men",
    "hey woman", "hey lewman", "hey lew man", "hey lu min", "hey loom in",
    "oi lumen", "right lumen", "okay lumen",
    "blue moon", "blue moons", "hey blue moon", "bloom in", "bloom on",
)

# Vosk often mishears "Lumen" as these — treat as wake, never as a search command.
_LUMEN_PHANTOMS = frozenset({
    "blue moon", "blue moons", "bloom", "blooming", "bloom in", "bloom on",
    "bloo moon", "blew moon", "glue min", "lu min", "lew min", "loom in",
})

# Two-word British mishears: "lu min", "lew man", "loom in"
_WAKE_TWO_WORD = re.compile(
    r"\b(lu|lew|lou|loom|luke|new|room)\s+(men|man|min|mun|mon|men|in|min)\b",
    re.I,
)

def _grocery_destinations() -> frozenset[str]:
    try:
        from ui.grocery_control import GROCERY_STORES
        return frozenset(GROCERY_STORES)
    except ImportError:
        return frozenset()


_SINGLE_DESTINATIONS = frozenset({
    "youtube", "google", "maps", "github", "netflix", "spotify", "gmail",
    "amazon", "reddit", "wikipedia", "facebook", "instagram", "twitter",
    "outlook",
}) | _grocery_destinations()

_ACTION_VERBS = frozenset({
    "open", "go", "search", "find", "play", "show", "navigate", "load",
    "visit", "watch", "map", "get", "weather", "directions", "close",
    "stop", "pause", "reload", "back", "forward", "summarize", "translate",
    "buy", "shop", "listen", "stream", "mute", "unmute", "volume", "select",
    "choose", "pick", "click", "louder", "quieter",
})

_MEDIA_SHORT_COMMANDS = frozenset({
    "back", "mute", "unmute", "pause", "play", "stop", "louder", "quieter",
})

_SCROLL_SHORT_COMMANDS = frozenset({
    "up",
})

_INCOMPLETE_PREFIXES = frozenset({
    "open", "go", "search", "find", "play", "show", "navigate", "load",
    "visit", "watch", "map", "get", "give", "bring", "take", "look",
    "start", "stop", "pause", "can", "could",
})

_NOISE = frozenset({
    "yeah", "yes", "yep", "ok", "okay", "no", "uh", "um", "hmm", "the", "a",
    "and", "but", "so", "well", "right", "like", "what", "that", "this",
    "shoot", "woman", "human", "hopefully", "choose", "cheated", "thoughts",
})

_GARBAGE_PHRASES = frozenset({
    "hopefully you choose", "open youtube cheated", "no moon", "shoot",
    "woman play the", "the moon", "you cheated", "hope and youtube",
    "and a huge you", "and you can", "you got to", "a new issue", "new shoe",
})

# Mishears of the JARVIS greeting picked up from speakers.
_TTS_GARBAGE = (
    "oh for new true",
    "for new true",
    "at your service",
    "your service",
    "oh for you",
    "for you true",
    "service josh",
    "service sir",
    "at your",
    "oh for",
)


def compact_alpha(text: str) -> str:
    return re.sub(r"[^a-z]", "", text.lower())


def is_lumen_phantom(text: str) -> bool:
    """True when STT misheard the wake word as something like 'blue moon'."""
    t = normalize_command(text).lower().strip()
    if not t:
        return False
    if t in _LUMEN_PHANTOMS:
        return True
    if re.fullmatch(r"blue\s+moon?s?", t):
        return True
    compact = compact_alpha(t)
    return compact in {"bluemoon", "bluemon", "bloomin", "bluemoons"}


def _edit_distance(a: str, b: str) -> int:
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        curr = [i]
        for j, cb in enumerate(b, 1):
            cost = 0 if ca == cb else 1
            curr.append(min(prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + cost))
        prev = curr
    return prev[-1]


def _word_is_wake(word: str) -> bool:
    w = compact_alpha(word)
    if len(w) < 3:
        return False
    if w in _WAKE_MISHEARS:
        return True
    if "lumen" in w or "lumin" in w:
        return True
    if w.startswith(("lu", "lew", "lou", "loom")) and len(w) <= 8:
        if _edit_distance(w, "lumen") <= 3:
            return True
    return 4 <= len(w) <= 10 and _edit_distance(w, "lumen") <= 2


def _compact_near_lumen(compact: str) -> bool:
    if not compact or len(compact) < 4:
        return False
    if "lumen" in compact or "lumin" in compact:
        return True
    if len(compact) <= 10 and _edit_distance(compact[:6], "lumen") <= 2:
        return True
    for i in range(len(compact) - 3):
        chunk = compact[i : i + 6]
        if len(chunk) >= 4 and _edit_distance(chunk, "lumen") <= 2:
            return True
    return False


def matches_wake(text: str) -> bool:
    """True when speech contains the wake word (including British mishears)."""
    t = text.lower().strip()
    if not t:
        return False
    if is_lumen_phantom(t):
        return True
    if re.search(r"\bblue\s+moon?s?\b", t):
        return True
    if _WAKE_TWO_WORD.search(t):
        return True
    compact = compact_alpha(t)
    if _compact_near_lumen(compact):
        return True
    if re.search(r"\b(loom\s*in|lu\s*men|lew\s*men|lou\s*men|lu\s*min)\b", t):
        return True
    words = re.findall(r"[a-z']+", t)
    if not words:
        return False
    for w in words[:4]:
        if _word_is_wake(w):
            return True
    start = 0
    if words[0] in ("hey", "hi", "ok", "a", "oi", "right", "okay") and len(words) > 1:
        start = 1
    if _word_is_wake(words[start]):
        return True
    return False


def strict_wake(text: str) -> bool:
    return matches_wake(text)


def strip_wake_text(text: str) -> str:
    """Remove wake word from the start of an utterance."""
    t = text.strip()
    lower = t.lower()
    for prefix in sorted(_WAKE_PREFIXES, key=len, reverse=True):
        if lower.startswith(prefix):
            return t[len(prefix):].strip(" ,.")
    if lower.startswith("lumen"):
        return t[5:].strip(" ,.")
    if lower.startswith("lumin"):
        return t[5:].strip(" ,.")
    words = t.split()
    if len(words) >= 2 and words[0].lower() in ("hey", "hi", "ok", "a"):
        if _word_is_wake(words[1]):
            return " ".join(words[2:]).strip(" ,.")
    if words and _word_is_wake(words[0]):
        return " ".join(words[1:]).strip(" ,.")
    for marker in ("lumen", "lumin"):
        idx = lower.find(marker)
        if idx >= 0:
            return (t[:idx] + t[idx + len(marker):]).strip(" ,.")
    return t.strip()


def normalize_command(text: str) -> str:
    """Fix common STT mishears ('can you tube' -> 'open youtube')."""
    t = text.strip()
    t = re.sub(r"\byou\s+tube\b", "youtube", t, flags=re.I)
    t = re.sub(r"\byou\s+to\b", "youtube", t, flags=re.I)
    t = re.sub(r"^(can|could|coln|cann|gun|gonna)\s+", "open ", t, flags=re.I)
    t = re.sub(r"\bfollow\s+me\s+up\b", "volume up", t, flags=re.I)
    t = re.sub(r"\bfollow\s+me\s+down\b", "volume down", t, flags=re.I)
    t = re.sub(r"\bturn\s+it\s+up\b", "volume up", t, flags=re.I)
    t = re.sub(r"\bturn\s+it\s+down\b", "volume down", t, flags=re.I)
    return t.strip()


def is_tts_garbage(text: str) -> bool:
    """True when STT likely picked up the assistant's own voice or noise."""
    lower = normalize_command(text).lower().strip()
    if not lower:
        return True
    if is_lumen_phantom(lower):
        return True
    if lower in _GARBAGE_PHRASES:
        return True
    if any(g in lower for g in _TTS_GARBAGE):
        return True
    words = lower.split()
    if len(words) <= 2 and words and words[0] in {"shoot", "woman", "human", "hopefully", "thoughts"}:
        return True
    return False


def _has_action_intent(lower: str, words: list[str]) -> bool:
    if any(w in _SINGLE_DESTINATIONS for w in words):
        return True
    if any(w in _ACTION_VERBS for w in words):
        return True
    return lower.startswith(("what ", "where ", "how ", "who ", "when ", "why "))


def continues_partial(partial: str, new: str) -> bool:
    """True when new speech completes an in-progress command like 'open …'."""
    if not is_incomplete_phrase(partial):
        return True
    if is_tts_garbage(new):
        return False
    combined = normalize_command(f"{partial} {new}")
    if is_tts_garbage(combined):
        return False
    if is_incomplete_phrase(combined):
        new_words = normalize_command(new).lower().split()
        if any(w in _SINGLE_DESTINATIONS for w in new_words):
            return True
        partial_l = normalize_command(partial).lower().strip()
        if partial_l in ("search", "search for", "add", "put", "get", "buy", "include"):
            return bool(new_words) and new_words[0] not in _NOISE
    return looks_like_command(combined)


def is_wake_only(message: str) -> bool:
    msg = message.strip()
    if not msg:
        return True
    if not matches_wake(msg):
        return False
    rest = strip_wake_text(msg)
    return len(rest) <= 2


def is_incomplete_phrase(text: str) -> bool:
    t = normalize_command(text).strip().lower()
    if not t:
        return True
    words = t.split()
    if len(words) >= 2:
        return False
    word = words[0]
    if word in _SINGLE_DESTINATIONS:
        return False
    if word in _SCROLL_SHORT_COMMANDS:
        return False
    if word in _INCOMPLETE_PREFIXES:
        return True
    if word in _NOISE:
        return True
    return len(word) < 5


def looks_like_command(text: str) -> bool:
    """Reject noise / TTS echo / nonsense before executing."""
    t = normalize_command(text)
    if len(t) < 4:
        return False
    lower = t.lower()
    if lower in _NOISE or is_tts_garbage(t):
        return False
    if is_incomplete_phrase(t):
        return False
    words = lower.split()
    if len(words) == 1:
        return (
            words[0] in _SINGLE_DESTINATIONS
            or words[0] in _MEDIA_SHORT_COMMANDS
            or words[0] in _SCROLL_SHORT_COMMANDS
        )
    if re.match(r"^(volume\s+(?:up|down)|turn\s+(?:up|down)(?:\s+volume)?)$", lower):
        return True
    if re.match(r"^(first|top)\s+video$", lower):
        return True
    if re.search(
        r"\b(?:first|1st|second|2nd|third|3rd|fourth|4th|fifth|5th)\s+video\b",
        lower,
    ):
        return True
    if re.search(
        r"\b(?:play|watch|select|open)\s+(?:the\s+)?(?:first|second|third|1st|2nd|3rd)\s+video\b",
        lower,
    ):
        return True
    if re.search(r"\b(?:open|go to|launch|start)\s+(youtube|google|gmail|maps|spotify|netflix|tesco|asda|sainsburys|morrisons)\b", lower):
        return True
    if re.search(r"\b(?:add|put|get|buy)\s+\w+", lower):
        return True
    if lower in _SCROLL_SHORT_COMMANDS:
        return True
    if re.search(
        r"\b(?:scroll(?:\s+(?:down|up))?(?:\s+(?:a\s+)?(?:bit|little))?|"
        r"start\s+scroll(?:ing)?|stop\s+scroll(?:ing)?|nudge\s+up)\b",
        lower,
    ):
        return True
    if re.search(r"^search(?:\s+for)?\s+\w+", lower) and not re.search(
        r"\b(?:the web|on google|online)\b", lower
    ):
        return True
    if re.search(r"\b(?:weather|play music|read (?:this|the) page|open settings)\b", lower):
        return True
    if lower in (
        "weather", "play music", "open settings", "read page", "read aloud",
        "go back", "new tab", "stop listening",
    ):
        return True
    if lower.startswith(("tell me ", "describe ", "help me ", "talk about ")):
        return True
    return _has_action_intent(lower, words)


def is_meaningful_voice(text: str) -> bool:
    """Looser gate for always-on voice — accept questions and short commands."""
    t = normalize_command(text).strip()
    if len(t) < 2 or is_tts_garbage(t) or is_wake_only(t) or is_lumen_phantom(t):
        return False
    if "?" in t:
        return True
    return looks_like_command(t)
