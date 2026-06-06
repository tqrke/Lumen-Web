"""JARVIS-style intent routing — turns natural language into browser actions."""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import quote, quote_plus


@dataclass
class IntentResult:
    reply: str
    kind: str  # navigate | search | new_tab | back | forward | reload | summarize | answer
    payload: str = ""
    speak: bool = True


_PLACE_TYPOS = {
    "lindon": "London",
    "landon": "London",
    "londom": "London",
    "londin": "London",
    "paris france": "Paris, France",
    "new york city": "New York, NY",
}


def _clean(text: str) -> str:
    t = text.strip()
    t = re.sub(
        r"^(please|can you|could you|i want|i need|i'd like|help me|show me|get me|give me)\s+",
        "",
        t,
        flags=re.I,
    )
    t = re.sub(r"^(a|an|the)\s+", "", t, flags=re.I)
    return t.strip(" .!?,")


def _normalize_place(place: str) -> str:
    p = _clean(place)
    p = re.sub(r"\b(google maps|google map|google|maps?)\b", "", p, flags=re.I).strip(" ,")
    low = p.lower()
    for typo, fix in _PLACE_TYPOS.items():
        if low == typo or low.startswith(typo + " "):
            return fix
    return p[:120] if p else ""


def _extract_after(message: str, patterns: list[str]) -> str | None:
    lower = message.lower().strip()
    for pat in patterns:
        m = re.search(pat, lower, re.I)
        if m:
            raw = message[m.start(1):m.end(1)] if m.lastindex else message
            return _clean(raw)
    return None


def _maps_url(place: str) -> str:
    q = quote_plus(_normalize_place(place))
    return f"https://www.google.com/maps/search/?api=1&query={q}"


def _directions_url(dest: str, origin: str = "") -> str:
    dest = _normalize_place(dest)
    if origin:
        return (
            "https://www.google.com/maps/dir/?api=1"
            f"&origin={quote_plus(origin)}&destination={quote_plus(dest)}"
        )
    return f"https://www.google.com/maps/dir/?api=1&destination={quote_plus(dest)}"


def _weather_url(place: str) -> str:
    return f"https://www.google.com/search?q=weather+in+{quote_plus(_normalize_place(place))}"


def _youtube_url(query: str) -> str:
    return f"https://www.youtube.com/results?search_query={quote_plus(_clean(query))}"


def _web_search_url(query: str) -> str:
    return f"https://www.google.com/search?q={quote_plus(_clean(query))}"


def _images_url(query: str) -> str:
    return f"https://www.google.com/search?tbm=isch&q={quote_plus(_clean(query))}"


def _news_url(topic: str) -> str:
    return f"https://news.google.com/search?q={quote_plus(_clean(topic))}"


def _wiki_url(topic: str) -> str:
    slug = _clean(topic).replace(" ", "_")
    return f"https://en.wikipedia.org/wiki/{quote(slug)}"


def _translate_url(text: str, lang: str) -> str:
    return f"https://translate.google.com/?sl=auto&tl={quote_plus(lang)}&text={quote_plus(text)}"


def _flight_url(query: str) -> str:
    return f"https://www.google.com/travel/flights?q={quote_plus(_clean(query))}"


def _stock_url(symbol: str) -> str:
    sym = symbol.upper().strip()
    return f"https://www.google.com/search?q={quote_plus(sym + ' stock price')}"


def _time_url(place: str) -> str:
    return f"https://www.google.com/search?q=time+in+{quote_plus(_normalize_place(place))}"


def _calculator_url(expr: str) -> str:
    return f"https://www.google.com/search?q={quote_plus(expr)}"


def _shopping_url(query: str) -> str:
    return f"https://www.google.com/search?tbm=shop&q={quote_plus(_clean(query))}"


def _music_url(query: str) -> str:
    return f"https://open.spotify.com/search/{quote(_clean(query))}"


def _reddit_url(topic: str) -> str:
    return f"https://www.reddit.com/search/?q={quote_plus(_clean(topic))}"


def _github_url(query: str) -> str:
    q = _clean(query)
    if re.match(r"^[\w.-]+/[\w.-]+$", q):
        return f"https://github.com/{q}"
    return f"https://github.com/search?q={quote_plus(q)}&type=repositories"


def _wants_youtube(message: str) -> bool:
    lower = message.lower()
    return bool(re.search(r"\b(youtube|on youtube|youtube video|watch on youtube)\b", lower))


def _extract_maps_query(msg: str) -> str | None:
    return _extract_after(msg, [
        r"(?:open|get|give)(?:\s+me)?(?:\s+a)?\s+map(?:\s+of)?\s+(.+)$",
        r"(?:map|maps)\s+(?:of|for|in|showing)\s+(.+)$",
        r"(?:show|display|find).*(?:map|maps).*(?:of|for|in|showing)?\s*(.+)$",
        r"^where is (.+)\??$",
        r"^locate (.+)$",
        r"^(.+)\s+on (?:a )?map$",
    ])


def is_wake_only(message: str) -> bool:
    from ui.wake_words import is_wake_only as _wake_only
    return _wake_only(message)


def _strip_voice_prefix(msg: str) -> str:
    from ui.wake_words import strip_wake_text
    return strip_wake_text(msg.strip())


_VIDEO_ORDINALS = {
    "first": 1, "1st": 1, "one": 1, "top": 1,
    "second": 2, "2nd": 2, "two": 2,
    "third": 3, "3rd": 3, "three": 3,
    "fourth": 4, "4th": 4, "four": 4,
    "fifth": 5, "5th": 5, "five": 5,
}

_VIDEO_ORDINAL_RE = re.compile(
    r"(?:\b(?:select|choose|pick|click|open|play|watch)\s+(?:the\s+)?"
    r"(first|1st|one|top|second|2nd|two|third|3rd|three|fourth|4th|four|fifth|5th|five)"
    r"(?:\s+(?:video|result|one)s?)?\s*$"
    r"|\b(?:select|choose|pick|click|open|play|watch)\s+(?:the\s+)?"
    r"(first|1st|one|top|second|2nd|two|third|3rd|three|fourth|4th|four|fifth|5th|five)"
    r"\s+(?:video|result|one)s?\b"
    r"|\b(?:first|1st|top|second|2nd|third|3rd|fourth|4th|fifth|5th)\s+video\b"
    r"|\bplay\s+(?:video\s+)?(?:number\s+)?([1-5])\b"
    r"|\bvideo\s+(?:number\s+)?([1-5])\b)",
    re.I,
)

_VIDEO_PAGE_SUFFIX = re.compile(
    r"\s+(?:on|from|in|at)\s+(?:the\s+)?(?:home\s*page|homepage|youtube|main\s*page|feed)\s*$",
    re.I,
)


def _parse_video_ordinal(lower: str) -> int | None:
    lower = _VIDEO_PAGE_SUFFIX.sub("", lower).strip()
    m = _VIDEO_ORDINAL_RE.search(lower)
    if not m:
        return None
    token = (m.group(1) or m.group(2) or m.group(3) or "").lower()
    if token.isdigit():
        n = int(token)
        return n if 1 <= n <= 5 else None
    return _VIDEO_ORDINALS.get(token)


def _strip_item_quotes(item: str) -> str:
    return item.strip().strip("\"'“”‘’")


def _match_grocery(lower: str) -> tuple[str, str] | None:
    """Tesco grocery — search, add, open store, basket."""
    from ui.grocery_control import GROCERY_STORES, normalize_item

    if re.match(r"^(?:show|view|open)\s+(?:my\s+)?(?:basket|cart|trolley|bag)$", lower):
        return ("basket", "Opening your basket.")

    # "search spaghetti" / "search for milk" → Tesco only (not web search)
    if not re.search(r"\b(?:the web|on google|on the internet|online)\b", lower):
        m = re.search(
            r"(?:^|\b)search(?:\s+for)?\s+(.+?)(?:\s+on\s+tesco)?\s*$",
            lower,
        )
        if m:
            item = normalize_item(_strip_item_quotes(m.group(1)))
            if item and len(item) >= 2 and item not in ("it", "that", "this", "one"):
                return (f"search:{item}", f"Searching Tesco for {item}.")

    m = re.search(
        r"\b(?:add|put|get|buy|include)\s+(?:some\s+)?(.+?)"
        r"(?:\s+(?:to|in|into)\s+(?:my\s+)?(?:basket|cart|trolley|bag))?\s*$",
        lower,
    )
    if m:
        item = normalize_item(m.group(1))
        if item and len(item) >= 2 and item not in ("it", "that", "this", "one"):
            return (f"add:{item}", f"Adding {item} to your basket.")

    if lower in GROCERY_STORES:
        name = lower.title()
        return (f"open:{lower}", f"Opening {name}.")

    return None


def _match_scroll_control(lower: str) -> tuple[str, str] | None:
    """Slow continuous page scroll — say stop to halt; scroll up nudges back a little."""
    if re.match(
        r"^(?:stop(?:\s+scroll(?:ing)?)?|halt(?:\s+scroll(?:ing)?)?)$",
        lower,
    ):
        return ("stop", "Stopped scrolling.")
    if re.match(
        r"^(?:up(?:\s+(?:a\s+)?(?:bit|little))?|"
        r"scroll\s+up(?:\s+(?:a\s+)?(?:bit|little|tiny|slightly))?|"
        r"scroll\s+(?:you|uo|oop|upward)(?:\s+(?:a\s+)?(?:bit|little))?|"
        r"nudge\s+up(?:\s+(?:a\s+)?(?:bit|little))?|"
        r"tiny\s+scroll\s+up|scroll\s+back\s+up|go\s+back\s+up\s+(?:a\s+)?(?:bit|little)?|"
        r"(?:scope|scott|scrope|scoop))$",
        lower,
    ):
        return ("nudge_up", "Scrolled up a little.")
    if re.match(
        r"^(?:scroll(?:\s+down)?|start\s+scroll(?:ing)?|keep\s+scroll(?:ing)?|"
        r"scroll\s+the\s+page|auto\s+scroll|begin\s+scroll(?:ing)?)$",
        lower,
    ):
        return ("start", "Scrolling slowly. Say stop when you're done.")
    return None


def _match_media_control(lower: str) -> tuple[str, str] | None:
    ordinal = _parse_video_ordinal(lower)
    if ordinal is not None:
        n = ordinal
        label = ("first", "second", "third", "fourth", "fifth")[n - 1] if n <= 5 else str(n)
        return (f"video_{n}", f"Playing the {label} video.")
    if re.search(
        r"\b(?:select|choose|pick|click|open|play|watch)\s+(?:the\s+)?(?:first|1st|top)\s+(?:video|result)\b",
        lower,
    ) or re.match(
        r"^(?:first|top)\s+video$|^(?:play|open|select)\s+(?:the\s+)?first\s+(?:one|video)$",
        lower,
    ):
        return ("video_1", "Opening the first video.")
    if re.search(
        r"\b(volume\s+up|turn\s+(?:the\s+)?volume\s+up|louder|increase\s+(?:the\s+)?volume)\b",
        lower,
    ) or re.match(r"^(?:volume\s+up|turn\s+up(?:\s+volume)?|louder|turn\s+it\s+up)$", lower):
        return ("volume_up", "Turning volume up.")
    if re.search(
        r"\b(volume\s+down|turn\s+(?:the\s+)?volume\s+down|quieter|decrease\s+(?:the\s+)?volume)\b",
        lower,
    ) or re.match(r"^(?:volume\s+down|turn\s+down(?:\s+volume)?|quieter|turn\s+it\s+down)$", lower):
        return ("volume_down", "Turning volume down.")
    if re.search(
        r"\b(?:stop|halt)\b.*\b(music|video|song|playback|media|audio)\b",
        lower,
    ) or re.match(
        r"^(?:stop|halt)\s+(?:the\s+)?(?:music|video|song|playback|media|audio)\b",
        lower,
    ):
        return ("stop", "Stopping playback.")
    if re.match(r"^(?:pause|halt)\s+(?:the\s+)?(?:music|video|song|playback|media|audio)\b", lower):
        return ("pause", "Pausing playback.")
    if re.search(
        r"\b(resume|unpause|continue)\b(?:\s+(?:the|this))?\s*(?:music|video|song|playback|media)?\s*$",
        lower,
    ):
        return ("play", "Resuming playback.")
    if re.match(r"^(?:play|resume)\s+(?:the\s+)?(?:music|video|song|playback)\s*$", lower):
        return ("play", "Resuming playback.")
    if re.search(r"\bunmute\b", lower):
        return ("unmute", "Unmuted.")
    if re.search(r"\bmute\b", lower):
        return ("mute", "Muted.")
    return None


def is_fast_command(message: str) -> bool:
    from ui.command_sanitize import sanitize_command
    from ui.wake_words import normalize_command

    msg = sanitize_command(normalize_command(_strip_voice_prefix(message.strip())))
    if not msg:
        return False
    lower = msg.lower()
    if re.match(
        r"^(go back|back|previous page|take me back|navigate back|forward|go forward|"
        r"reload|refresh|new tab|open tab)$",
        lower,
    ):
        return True
    if re.match(
        r"^(?:open|go to|go|visit|load)\s+"
        r"(youtube|google|maps|github|netflix|spotify|gmail|amazon|reddit|wikipedia)\s*$",
        lower,
    ):
        return True
    return _match_media_control(lower) is not None


def should_use_browser_intent(message: str, page_url: str = "", page_title: str = "") -> bool:
    """True when the utterance should control the browser — not free-form chat."""
    from ui.command_router import is_fast_phrase, match_fast_command
    from ui.command_sanitize import expand_video_command, looks_like_question, sanitize_command

    msg = expand_video_command(sanitize_command(message.strip()))
    if is_fast_phrase(msg) or is_fast_command(msg):
        return True
    fast = match_fast_command(msg)
    if fast and fast.kind in ("media", "grocery", "back", "forward", "reload", "new_tab", "summarize", "app"):
        return True
    intent = resolve_intent(msg, page_url, page_title)
    if not intent:
        return False
    if intent.kind in ("media", "grocery", "back", "forward", "reload", "new_tab", "summarize", "app"):
        return True
    if intent.kind == "navigate":
        if looks_like_question(msg):
            return False
        fb = fallback_search(msg)
        if intent.payload == fb.payload:
            return False
        return True
    return False


def resolve_intent(message: str, page_url: str = "", page_title: str = "") -> IntentResult | None:
    """Return an actionable intent, or None to fall through to LLM / generic search."""
    from ui.command_router import match_fast_command
    from ui.command_sanitize import voice_transcript

    fast = match_fast_command(message)
    if fast:
        return fast

    msg = voice_transcript(_strip_voice_prefix(message.strip()))
    if not msg:
        return None

    lower = msg.lower()

    if re.match(r"^(new tab|open tab)$", lower):
        return IntentResult("Opening a new tab.", "new_tab")
    if re.match(r"^(go back|back|previous page)$", lower):
        return IntentResult("Going back.", "back")
    if re.match(r"^(forward|go forward|next page)$", lower):
        return IntentResult("Moving forward.", "forward")
    if re.match(r"^(reload|refresh|reload page)$", lower):
        return IntentResult("Refreshing the page.", "reload")
    if re.search(r"summarize|summary|tl;dr|what is this page", lower):
        return IntentResult("Analyzing this page…", "summarize")

    lower_for_media = _VIDEO_PAGE_SUFFIX.sub("", lower).strip()
    lower_for_media = re.sub(r"\s+of\s+youtube\s*$", "", lower_for_media, flags=re.I)
    media = _match_media_control(lower_for_media)
    if media:
        return IntentResult(media[1], "media", media[0])

    grocery = _match_grocery(lower)
    if grocery:
        return IntentResult(grocery[1], "grocery", grocery[0])

    # Maps first — before generic open/search
    maps_q = _extract_maps_query(msg)
    if maps_q and len(maps_q) > 1:
        place = _normalize_place(maps_q)
        return IntentResult(
            f"Opening map of {place}.",
            "navigate",
            _maps_url(place),
        )

    directions = _extract_after(msg, [
        r"directions?(?:\s+to|\s+for)?\s+(.+)$",
        r"how (?:do i|to) get to (.+)\??$",
        r"route to (.+)$",
        r"navigate to (.+)$",
    ])
    if directions and "map" not in lower[:14]:
        dest = _normalize_place(directions)
        return IntentResult(
            f"Directions to {dest}.",
            "navigate",
            _directions_url(dest),
        )

    weather = _extract_after(msg, [
        r"weather(?:\s+in|\s+for|\s+at|\s+of)?\s+(.+)$",
        r"(?:what(?:'s| is) the weather(?: like)?(?: in| for| at)?)\s+(.+)\??$",
        r"^(.+)\s+weather\??$",
    ])
    if weather or re.search(r"\bweather\b", lower):
        place = _normalize_place(weather or re.sub(r".*weather", "", lower))
        if place:
            return IntentResult(
                f"Weather for {place}.",
                "navigate",
                _weather_url(place),
            )

    # YouTube only when explicitly requested
    if _wants_youtube(msg):
        video = _extract_after(msg, [
            r"(?:play|watch|search)(?:\s+on youtube|\s+youtube)?\s+(?:for\s+)?(.+)$",
            r"youtube\s+(?:search\s+)?(?:for\s+)?(.+)$",
        ])
        q = video or _clean(re.sub(r".*youtube", "", lower))
        if q:
            return IntentResult(f"YouTube: {q}.", "navigate", _youtube_url(q))

    video = _extract_after(msg, [
        r"(?:play|watch)(?:\s+me)?\s+(?:the\s+)?video(?:\s+of|\s+about)?\s+(.+)$",
    ])
    if video and re.search(r"\bvideo\b", lower):
        return IntentResult(f"Searching video for {video}.", "navigate", _youtube_url(video))

    images = _extract_after(msg, [
        r"(?:show|find|search for|get)(?:\s+me)?\s+(?:pictures?|photos?|images?)\s+(?:of\s+)?(.+)$",
        r"(?:pictures?|photos?|images?)\s+of\s+(.+)$",
    ])
    if images:
        return IntentResult(f"Images of {images}.", "navigate", _images_url(images))

    news = _extract_after(msg, [
        r"(?:latest\s+)?news(?:\s+about|\s+on|\s+for|\s+in)?\s+(.+)$",
        r"what(?:'s| is) happening(?: in| with)?\s+(.+)\??$",
    ])
    if news or (re.search(r"\bnews\b", lower) and len(msg) > 8):
        topic = news or _clean(msg)
        return IntentResult(f"News: {topic}.", "navigate", _news_url(topic))

    wiki = _extract_after(msg, [
        r"^(?:what is|what's|who is|who's|tell me about|explain|define)\s+(.+)\??$",
        r"^(.+)\s+(?:wikipedia|wiki)\??$",
    ])
    if wiki and len(wiki) > 2:
        return IntentResult(f"Wikipedia: {wiki}.", "navigate", _wiki_url(wiki))

    tr = re.search(
        r"translate\s+['\"]?(.+?)['\"]?\s+(?:to|into)\s+(\w+)",
        msg,
        re.I,
    )
    if tr:
        text, lang = tr.group(1), tr.group(2)
        return IntentResult(f"Translating to {lang}.", "navigate", _translate_url(text, lang))

    flights = _extract_after(msg, [
        r"flights?(?:\s+to|\s+from|\s+between)?\s+(.+)$",
        r"book a flight(?:\s+to)?\s+(.+)$",
    ])
    if flights or "flight" in lower:
        q = flights or msg
        return IntentResult("Searching flights.", "navigate", _flight_url(q))

    stock = _extract_after(msg, [
        r"(?:stock|share) (?:price )?(?:of|for)\s+(.+)$",
        r"^(.+)\s+stock(?:\s+price)?\??$",
    ])
    if stock or re.search(r"\bstock price\b", lower):
        sym = stock or _clean(re.sub(r"stock.*", "", lower))
        return IntentResult(f"Stock: {sym}.", "navigate", _stock_url(sym))

    tz = _extract_after(msg, [
        r"time(?:\s+in|\s+at|\s+for)?\s+(.+)\??$",
        r"what time is it in (.+)\??$",
    ])
    if tz:
        place = _normalize_place(tz)
        return IntentResult(f"Time in {place}.", "navigate", _time_url(place))

    calc = _extract_after(msg, [
        r"^(?:calculate|compute|what is|what's)\s+(.+)\??$",
    ])
    if calc and re.search(r"[\d+\-*/^%]", calc):
        return IntentResult(f"Calculating {calc}.", "navigate", _calculator_url(calc))

    shop = _extract_after(msg, [
        r"(?:buy|shop(?:ping)?(?:\s+for)?|find(?:\s+me)?)\s+(.+)$",
        r"where (?:can i|to) buy\s+(.+)\??$",
    ])
    if shop:
        return IntentResult(f"Shopping: {shop}.", "navigate", _shopping_url(shop))

    music = _extract_after(msg, [
        r"(?:play|listen to|stream)\s+(?:music\s+)?(.+)$",
        r"(?:song|track|album)\s+(.+)$",
    ])
    if music and not _wants_youtube(msg) and not re.search(r"\bvideo\b", lower):
        mq = music.strip().lower()
        if re.match(
            r"^the (first|second|third|fourth|fifth|1st|2nd|3rd|4th|5th|one|two|three|four|five)$",
            mq,
        ):
            from ui.command_sanitize import expand_video_command
            ordinal_media = _match_media_control(expand_video_command(f"play {mq}"))
            if ordinal_media:
                return IntentResult(ordinal_media[1], "media", ordinal_media[0])
        elif not re.match(
            r"^(the )?(first|second|third|fourth|fifth|1st|2nd|3rd|4th|5th|one|two|three|four|five)$",
            mq,
        ):
            return IntentResult(f"Music: {music}.", "navigate", _music_url(music))

    reddit = _extract_after(msg, [
        r"reddit(?:\s+search|\s+for)?\s+(.+)$",
        r"(?:search reddit for)\s+(.+)$",
    ])
    if reddit or lower.startswith("r/"):
        q = reddit or msg
        return IntentResult("Searching Reddit.", "navigate", _reddit_url(q))

    gh = _extract_after(msg, [
        r"github\s+(.+)$",
        r"(?:find|search)(?:\s+repo)?(?:\s+on github)?\s+(.+)$",
    ])
    if gh or "github" in lower:
        q = gh or _clean(re.sub(r"github", "", lower))
        return IntentResult("Searching GitHub.", "navigate", _github_url(q))

    search = _extract_after(msg, [
        r"^(?:search\s+the\s+web(?:\s+for)?|web search for|find on (?:the )?web|google)\s+(.+)$",
        r"^(?:look up|lookup)\s+(.+)$",
    ])
    if search:
        return IntentResult(f"Searching the web for \"{search}\".", "navigate", _web_search_url(search))

    go = _extract_after(msg, [
        r"(?:go to|open|visit|navigate to|take me to|bring up|load)\s+(.+)$",
        r"^(?:www\.|https?://)(.+)$",
    ])
    if go:
        target = go if re.match(r"^https?://", go, re.I) else go
        if re.match(r"^[\w.-]+\.[a-z]{2,}", target, re.I):
            url = target if target.startswith("http") else f"https://{target}"
            return IntentResult(f"Opening {target}.", "navigate", url)
        from ui.grocery_control import GROCERY_STORES
        sites = {
            "youtube": "https://www.youtube.com",
            "google": "https://www.google.com",
            "maps": "https://www.google.com/maps",
            "github": "https://github.com",
            "wikipedia": "https://wikipedia.org",
            "reddit": "https://www.reddit.com",
            "twitter": "https://x.com",
            "x": "https://x.com",
            "facebook": "https://www.facebook.com",
            "instagram": "https://www.instagram.com",
            "netflix": "https://www.netflix.com",
            "amazon": "https://www.amazon.com",
            "spotify": "https://open.spotify.com",
            "gmail": "https://mail.google.com",
            "outlook": "https://outlook.live.com",
            **GROCERY_STORES,
        }
        key = target.lower().split()[0]
        if key in sites and len(target.split()) <= 2:
            return IntentResult(f"Opening {key.title()}.", "navigate", sites[key])

    if re.match(r"^[\w.-]+\.[a-z]{2,}(/.*)?$", msg, re.I):
        url = msg if msg.startswith("http") else f"https://{msg}"
        return IntentResult(f"Opening {msg}.", "navigate", url)

    return None


def fallback_search(message: str) -> IntentResult:
    q = _clean(message)
    return IntentResult(
        f"Searching the web for \"{q}\".",
        "navigate",
        _web_search_url(q),
    )
