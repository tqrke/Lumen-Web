"""Clean up voice STT output before intent routing."""

from __future__ import annotations

import re

from ui.wake_words import normalize_command

def _known_sites() -> frozenset[str]:
    try:
        from ui.grocery_control import GROCERY_STORES
        grocery = frozenset(GROCERY_STORES)
    except ImportError:
        grocery = frozenset()
    return frozenset({
        "youtube", "google", "maps", "github", "netflix", "spotify", "gmail",
        "amazon", "reddit", "wikipedia", "facebook", "instagram", "twitter",
        "outlook", "x",
    }) | grocery


_SITES = _known_sites()

_OPEN_VERBS = frozenset({
    "open", "go", "visit", "load", "play", "show", "navigate", "bring",
})

_TRAILING_NOISE = frozenset({
    "put", "up", "it", "the", "a", "an", "please", "now", "ok", "okay",
    "yeah", "uh", "um", "to", "do", "so", "and", "me", "my",
})

_VIDEO_ORDINAL = (
    r"first|second|third|fourth|fifth|1st|2nd|3rd|4th|5th|one|two|three|four|five|top"
)
_TRUNCATED_VIDEO_RE = re.compile(
    rf"^(?:play|open|watch|select|click)\s+(?:the\s+)?({_VIDEO_ORDINAL})(?:\s+video)?$",
    re.I,
)
_BARE_ORDINAL_VIDEO_RE = re.compile(
    rf"^(?:the\s+)?({_VIDEO_ORDINAL})\s+video$",
    re.I,
)

_QUESTION_RE = re.compile(
    r"(?:^|\b)(what|who|why|how|when|where|which|tell me|explain|describe|define|"
    r"can you|could you|please help|help me|what's|whats|what is|who is|who's|"
    r"how's|hows|how is|how are|how do|how does|how did|how many|how much|how long|"
    r"how old|how far|how tall|how big|is there|are there|do you|does|did|would|"
    r"should|will you|may i|talk about|chat about|i want to know|give me)\b",
    re.I,
)

_STT_FIXES = (
    (r"\bopen\s+put\b", "open youtube"),
    (r"\bopen\s+u\s+tube\b", "open youtube"),
    (r"\bopen\s+you\s+to\b", "open youtube"),
    (r"\bopen\s+tube\b", "open youtube"),
    (r"\bopen\s+you\s+tube\b", "open youtube"),
    (r"\bgo\s+put\b", "go youtube"),
    (r"\bgo\s+tube\b", "go youtube"),
    (r"\bcan\s+youtube\b", "open youtube"),
    (r"\bplay\s+you\s+tube\b", "open youtube"),
    (r"^blue\s+moon\s+", ""),
    (r"^blue\s+moon?s?\s*$", ""),
    (r"\bopen\s+you\s+chew\b", "open youtube"),
    (r"\bopen\s+you\s+choose\b", "open youtube"),
    (r"\bopen\s+you\s+cheat\b", "open youtube"),
    (r"\bopen\s+you\s+cheated\b", "open youtube"),
    (r"\bopen\s+youtube\s+cheated\b", "open youtube"),
    (r"\bopen\s+you\b(?!\s*(?:tube|chew|choose|cheat|cheated|to))", "open youtube"),
    (r"\bopen\s+new\s+tube\b", "open youtube"),
    (r"\bopen\s+u\s+cube\b", "open youtube"),
    (r"\bopen\s+g\s+mail\b", "open gmail"),
    (r"\bopen\s+ge\s+mail\b", "open gmail"),
    (r"\bopen\s+g\s+oogle\b", "open google"),
    (r"\bsearch\s+the\s+weather\b", "weather"),
    (r"\bsearch\s+for\s+weather\b", "weather"),
    (r"\bplay\s+some\s+music\b", "play music"),
    (r"\bspagetti\b", "spaghetti"),
    (r"\badd\s+spagetti\b", "add spaghetti"),
    (r"\bsearch\s+spagetti\b", "search spaghetti"),
    (r"\bsearch\s+spaghett\b", "search spaghetti"),
    (r"\bsearch\s+for\s+spagetti\b", "search for spaghetti"),
    (r"\bsearch\s+for\s+spaghett\b", "search for spaghetti"),
    (r"\bat\s+spag\w+\s+add\s+spag\w+\b", "add spaghetti"),
    (r"\b\w+\s+spag\w+\s+add\s+spag\w+\b", "add spaghetti"),
    (r"\bokay\s+spag\w+\s+add\s+", "add "),
    (r"^you\s+tube$", "open youtube"),
    (r"^tube$", "open youtube"),
    (r"^you\s+choose\s*$", ""),
    (r"^choose\s*$", ""),
    (r"^when you choose\s*$", ""),
    (r"^when\s*$", ""),
    (r"^huh\s*$", ""),
    (r"^whoa\s*$", ""),
    (r"^hope that your shoe\s*$", ""),
    (r"\bhope\s+you\s+tube\b", "open youtube"),
    (r"\bhope\s+you\s+to\b", "open youtube"),
    (r"\bhope\s+and\s+(?:you\s+tube|youtube|tube)\b", "open youtube"),
    (r"\bopen\s+hope\s+and\b", "open"),
    (r"\bscroll\s+you\b", "scroll up"),
    (r"\bscroll\s+uo\b", "scroll up"),
    (r"\bscroll\s+oop\b", "scroll up"),
    (r"\bscroll\s+upward\b", "scroll up"),
)

_SCROLL_UP_MISHEARS = frozenset({
    "scope", "scott", "scrope", "skull", "scoop", "scoot",
})

_SCROLL_UP_RE = re.compile(
    r"\bscroll\s+(?:up|you|uo|oop|upward)(?:\s+(?:a\s+)?(?:bit|little|tiny|slightly))?\b",
    re.I,
)


_GROCERY_VOICE_RE = re.compile(
    r"\b((?:search(?:\s+for)?|add|put|get|buy|include)\s+(?:some\s+)?[a-z][\w\s-]{1,40})",
    re.I,
)

_GROCERY_PREFIX_ONLY = frozenset({
    "search", "search for", "add", "put", "get", "buy", "include",
})


def is_grocery_prefix_only(text: str) -> bool:
    """True when the user said only 'search' / 'add' — waiting for an item name."""
    return text.strip().lower() in _GROCERY_PREFIX_ONLY


def combine_grocery_prefix(prefix: str, rest: str) -> str:
    """Join 'search' + 'spaghetti' → 'search spaghetti'."""
    p = prefix.strip().lower()
    r = rest.strip()
    if not r:
        return p
    if p in ("search", "search for"):
        if r.lower().startswith("for "):
            return f"search {r[4:].strip()}"
        return f"search {r}"
    if p in ("add", "put", "get", "buy", "include"):
        return f"{p} {r}"
    return f"{p} {r}"


def merge_scroll_phrase(hint: str, *parts: str) -> str:
    """Combine 'scroll' + 'up' when STT splits them across grammar/stream."""
    texts = [hint.strip(), *(p.strip() for p in parts if p and p.strip())]
    combined = " ".join(texts).lower()
    if _SCROLL_UP_RE.search(combined):
        return "scroll up"
    if len(texts) >= 2 and texts[0].lower() == "scroll":
        for part in texts[1:]:
            w = part.lower().split()
            if w and w[0] in ("up", "you", "uo", "oop", "upward"):
                return "scroll up"
    if hint.strip().lower() == "scroll":
        for part in parts:
            pl = part.strip().lower()
            if pl in ("up", "you", "uo") or pl.startswith("up "):
                return "scroll up"
    return hint.strip()


def expand_scroll_command(text: str, *, scroll_context: bool = False) -> str:
    """Fix common STT mishears for scroll up."""
    t = text.strip()
    if not t:
        return text
    lower = t.lower()
    if _SCROLL_UP_RE.search(lower):
        return "scroll up"
    if lower in _SCROLL_UP_MISHEARS and scroll_context:
        return "scroll up"
    if lower == "up" or re.match(r"^up(?:\s+(?:a\s+)?(?:bit|little))?$", lower):
        return "scroll up"
    if lower in ("you", "uo") and scroll_context:
        return "scroll up"
    return t


def expand_grocery_command(text: str) -> str:
    """Pull Tesco commands out of noisy STT like 'at spaghetti add spaghetti'."""
    t = text.strip()
    if not t:
        return text
    lower = t.lower()
    if not re.search(r"\b(?:search|add|put|get|buy|include)\b", lower):
        return text
    if re.search(r"\b(?:the web|on google|online)\b", lower):
        return text
    matches = _GROCERY_VOICE_RE.findall(t)
    if matches:
        return sanitize_command(matches[-1].strip())
    return text


def expand_video_command(text: str) -> str:
    """Turn truncated STT like 'play the second' into 'play the second video'."""
    t = text.strip()
    if not t:
        return text
    lower = t.lower()
    m = _TRUNCATED_VIDEO_RE.match(lower)
    if m:
        return f"play the {m.group(1)} video"
    m = _BARE_ORDINAL_VIDEO_RE.match(lower)
    if m:
        return f"play the {m.group(1)} video"
    return text


def _infer_command(text: str) -> str:
    """Pull a likely everyday command out of garbled STT."""
    lower = text.lower().strip()
    if not lower:
        return text

    expanded = expand_video_command(lower)
    if expanded != lower:
        return expanded

    lower = re.sub(
        r"^(?:hope(?:fully)?|and|a|an|the|woman|human|no|can|could|just|like)\s+",
        "",
        lower,
    ).strip()

    if re.search(r"\b(you\s*tube|youtube|u\s*tube|tube|chew)\b", lower):
        if not re.search(
            r"\b(first|second|third|fourth|fifth|1st|2nd|3rd|4th|5th)\s+video\b",
            lower,
        ) and (
            re.search(r"\b(open|go|launch|start|visit|play|show|hope|load)\b", text.lower())
            or len(lower.split()) <= 4
        ):
            return "open youtube"

    if re.search(r"\bgoogle\b", lower) and re.search(
        r"\b(open|go|launch|start|visit|search)\b", text.lower()
    ):
        return "open google"

    if re.search(r"\bgmail\b", lower):
        return "open gmail"

    if re.search(r"\bmaps\b", lower) and re.search(r"\b(open|go|map)\b", text.lower()):
        return "open maps"

    if re.search(r"\bweather\b", lower):
        m = re.search(r"weather(?: in| for| at)?\s+(.+)", lower)
        place = (m.group(1).strip() if m else "").strip(" ?.")
        return f"weather {place}".strip() if place else "weather"

    if re.search(r"\bplay\b", lower) and re.search(r"\bmusic\b", lower):
        return "play music"

    m = re.search(
        r"\b(?:play|open|watch|select|click|woman)?\s*(?:the\s+)?"
        r"(first|second|third|fourth|fifth|1st|2nd|3rd|4th|5th)\s+video\b",
        lower,
    )
    if m:
        return f"play the {m.group(1)} video"

    m = re.search(
        r"\b(first|second|third|fourth|fifth|1st|2nd|3rd|4th|5th)\s+video\b",
        lower,
    )
    if m and (re.search(r"\bplay\b", lower) or len(lower.split()) <= 5):
        return f"play the {m.group(1)} video"

    if re.search(r"\bsettings\b", lower):
        return "open settings"

    try:
        from ui.grocery_control import GROCERY_STORES
        if lower in GROCERY_STORES:
            return f"open {lower}"
        for store in GROCERY_STORES:
            if re.search(rf"\b{re.escape(store)}\b", lower) and re.search(
                r"\b(open|go|launch|start|visit|shop)\b", lower
            ):
                return f"open {store}"
    except ImportError:
        pass

    return text


def light_transcript(text: str) -> str:
    """Minimal cleanup — preserve what the user said for Alexa-style routing."""
    from ui.wake_words import strip_wake_text
    t = normalize_command(strip_wake_text(text.strip()))
    if len(t) <= 1:
        return ""
    return t


def looks_like_question(text: str) -> bool:
    """True for questions / free-form chat — do not rewrite into site commands."""
    t = normalize_command(text.strip())
    if len(t) < 3:
        return False
    if "?" in t:
        return True
    if _QUESTION_RE.search(t):
        return True
    if re.search(
        r"\b(weather like|what time|how many|how much|how old|how long|how far|"
        r"tell me about|want to know|sky blue|works?|meaning of)\b",
        t,
        re.I,
    ):
        return True
    if re.match(
        r"^(hi|hello|hey|thanks|thank you|good morning|good night|chat|talk|help)\b",
        t,
        re.I,
    ):
        return True
    if len(t.split()) >= 6 and not re.match(
        r"^(open|go to|play|search|find|navigate|visit|load)\b",
        t,
        re.I,
    ):
        return True
    return False


def is_action_question(text: str) -> bool:
    """Questions that should open maps/weather/search — not spoken encyclopedia answers."""
    lower = normalize_command(text.strip()).lower()
    if re.search(r"\b(weather|forecast)\b", lower):
        return True
    if re.search(r"\b(directions|route to|navigate to|how (?:do i|to) get to)\b", lower):
        return True
    if re.search(r"\b(map of|maps of|show me.+(?:on )?(?:a )?map)\b", lower):
        return True
    if re.search(r"\b(time in|time at|what time is it in)\b", lower):
        return True
    if re.search(r"\b(stock price|share price|stock\b.*\bprice)\b", lower):
        return True
    if re.search(r"\b(flights? to|book a flight)\b", lower):
        return True
    if re.search(r"\btranslate\b.+\b(?:to|into)\b", lower):
        return True
    if re.search(r"^(search|find|look up|google|lookup)\b", lower):
        return True
    if re.search(r"\b(on youtube|youtube search|on github|on reddit)\b", lower):
        return True
    if re.search(r"\b(latest news|news about|news on|news for)\b", lower):
        return True
    if re.search(r"^(?:open|go to|visit|load)\s+", lower):
        return True
    if re.search(r"^(?:calculate|compute)\s+[\d]", lower):
        return True
    if re.search(r"^what(?:'s| is)\s+[\d+\-*/(]", lower):
        return True
    return False


def wants_spoken_answer(text: str) -> bool:
    """General knowledge / chat — answer out loud instead of opening a page."""
    return looks_like_question(text) and not is_action_question(text)


def is_voice_garbage(text: str) -> bool:
    """Random STT junk — never execute or show as a command."""
    t = normalize_command(text.strip()).lower()
    if not t or len(t) <= 1:
        return True
    if t in {
        "huh", "when", "whoa", "woah", "q", "uh", "um", "hm", "hmm",
        "when you choose", "you choose", "hope that your shoe",
        "when you", "each", "scale", "open", "you", "the", "hope", "put", "to", "shoo",
        "yeah", "yep", "yes", "no", "okay", "ok", "video", "the sec", "the idea",
        "hey this is", "this is", "a", "an", "and", "so", "it", "i", "im", "he",
        "she", "we", "they", "that", "this", "in", "on", "at", "of", "for",
        "the second", "second", "a video", "the video", "huh huh", "mm",
    }:
        return True
    # Single bare word that isn't a real one-word command
    words = t.split()
    if len(words) == 1 and words[0] not in {
        "youtube", "google", "gmail", "maps", "github", "netflix", "spotify",
        "reddit", "settings", "weather", "back", "forward", "reload", "refresh",
        "pause", "stop", "mute", "unmute", "summarize", "next", "skip", "play", "scroll",
        "home", "close",
    }:
        if len(words[0]) <= 4:
            return True
    if re.match(r"^(?:when|hope|huh|whoa|open|you|the)\s+(?:you|choose|tube|shoe|hope)\b", t):
        return True
    if re.search(r"\b(you choose|your shoe|hope that|open huge)\b", t):
        return True
    return False


def voice_transcript(text: str) -> str:
    """Voice output cleanup — preserve questions, infer only for commands."""
    raw = light_transcript(text)
    if not raw:
        return ""
    out = sanitize_command(raw, infer=not looks_like_question(raw))
    if out and not looks_like_question(out):
        out = expand_scroll_command(out)
        out = expand_grocery_command(out)
        out = expand_video_command(out)
    return out


_DIRECTIONAL_CMD = re.compile(
    r"^(?:volume|scroll|page|turn)\s+(?:up|down)$"
    r"|^(?:go\s+)?(?:back|forward)$"
    r"|^(?:zoom)\s+(?:in|out)$",
    re.I,
)


def sanitize_command(text: str, *, infer: bool = True) -> str:
    t = normalize_command(text.strip())
    if looks_like_question(t):
        return re.sub(r"\s+", " ", t).strip()
    for pat, repl in _STT_FIXES:
        t = re.sub(pat, repl, t, flags=re.I)

    t = re.sub(r"\byou\s+tube\b", "youtube", t, flags=re.I)
    t = re.sub(r"\byou\s+to\b", "youtube", t, flags=re.I)
    t = re.sub(r"\bu\s*tube\b", "youtube", t, flags=re.I)

    # Preserve directional commands (their trailing word is meaningful)
    if _DIRECTIONAL_CMD.match(t.strip()):
        return re.sub(r"\s+", " ", t).strip().lower()

    for site in _SITES:
        if re.search(rf"\bopen\s+{site}\b", t, flags=re.I):
            return f"open {site.lower()}"

    words = t.split()
    if len(words) >= 2:
        while len(words) > 1 and words[-1].lower() in _TRAILING_NOISE:
            words.pop()
        if len(words) == 2 and words[0].lower() in _OPEN_VERBS and words[1].lower() in _SITES:
            t = f"{words[0].lower()} {words[1].lower()}"
            return t
        t = " ".join(words)

    lower = t.lower().strip()
    for site in _SITES:
        if re.match(rf"^(?:open|go to|visit|load|play|bring up|take me to|navigate to)\s+{site}\s*$", lower):
            return f"open {site}"

    if not infer:
        return t.strip()

    if "?" in lower or re.search(
        r"^(what|who|why|how|when|where|which|tell me|explain|describe|can you|could you|"
        r"please help|help me|what's|whats|is there|are there)\b",
        lower,
    ):
        return t.strip()

    return _infer_command(t.strip())


def is_bare_site_open(text: str, site: str) -> bool:
    lower = sanitize_command(text).lower()
    return lower in (site, f"open {site}", f"go {site}", f"go to {site}", f"visit {site}")
