"""Built-in answers for all users — no Ollama or API keys required."""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request

_ANSWER_CACHE: dict[str, tuple[float, tuple[str, str | None]]] = {}
_CACHE_TTL_SEC = 900.0
_CACHE_MAX = 64

# Common voice mis-hears / short topics → Wikipedia search title
_TOPIC_ALIASES: dict[str, str] = {
    "ai": "Artificial intelligence",
    "ufo": "Unidentified flying object",
    "usa": "United States",
    "uk": "United Kingdom",
    "nfl": "National Football League",
    "nba": "National Basketball Association",
    "covid": "COVID-19",
    "wifi": "Wi-Fi",
    "dna": "DNA",
    "gpu": "Graphics processing unit",
    "cpu": "Central processing unit",
}

_WHY_WIKI: dict[str, str] = {
    "the sky blue": "Rayleigh scattering",
    "sky blue": "Rayleigh scattering",
    "the sky is blue": "Rayleigh scattering",
}


def _strip_articles(text: str) -> str:
    return re.sub(r"^(?:the|a|an)\s+", "", text.strip(), flags=re.I)


def _place_from_question(raw: str) -> str | None:
    m = re.search(
        r"\b(?:live in|living in|population of|people in|citizens of)\s+(.+)\??$",
        raw,
        re.I,
    )
    if m:
        return _strip_articles(_clean_topic(m.group(1)))
    return None


def _wiki_lookup_queries(topic: str, raw: str) -> list[str]:
    queries: list[str] = []
    key = topic.lower().strip()
    raw_key = _strip_articles(raw.lower()).strip()
    for hint_key, title in _WHY_WIKI.items():
        if hint_key in raw_key or hint_key in key:
            queries.append(title)
    alias = _TOPIC_ALIASES.get(key)
    if alias:
        queries.append(alias)
    stripped = _strip_articles(topic)
    place = _place_from_question(raw)
    for q in (place, stripped, topic, raw):
        if q and q.strip() and q.lower() not in {x.lower() for x in queries}:
            queries.append(q.strip())
    return queries


def _ddg_usable(text: str, query: str) -> bool:
    if len(text) < 28:
        return False
    if text.lstrip().startswith("."):
        return False
    if re.match(r"^what is\s+\w+$", query.strip(), re.I) and len(text) < 90:
        return False
    return True


def _fetch_json(url: str, timeout: float = 8.0) -> dict | list | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "LUMEN-Browser/2.1"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8", errors="replace"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError, ValueError):
        return None


def _clean_topic(text: str) -> str:
    t = text.strip().strip("?.!,")
    t = re.sub(
        r"^(please|can you|could you|tell me about|tell me|explain|describe|"
        r"what is|what are|what's|whats|who is|who was|who are|where is|"
        r"when was|when did|how does|how do|give me info on|info on|about)\s+",
        "",
        t,
        flags=re.I,
    )
    t = re.sub(r"\s+(please|for me)\s*$", "", t, flags=re.I)
    return t.strip()[:120]


def extract_topic(message: str) -> str:
    msg = message.strip()
    lower = msg.lower()
    patterns = [
        r"what is (.+)\??$",
        r"what are (.+)\??$",
        r"what's (.+)\??$",
        r"whats (.+)\??$",
        r"who is (.+)\??$",
        r"who was (.+)\??$",
        r"who are (.+)\??$",
        r"why (?:is|are|do|does|did|was|were) (.+)\??$",
        r"how many (.+)\??$",
        r"how much (.+)\??$",
        r"how long (.+)\??$",
        r"how old (.+)\??$",
        r"how (?:do|does|did|can|could|would|will) (.+)\??$",
        r"when (?:was|were|did|do|does) (.+)\??$",
        r"where (?:is|are|was|were) (.+)\??$",
        r"tell me about (.+)\??$",
        r"explain (.+)\??$",
        r"describe (.+)\??$",
        r"define (.+)\??$",
        r"give me (?:info on|information about) (.+)\??$",
        r"how does (.+) work\??$",
        r"where is (.+)\??$",
        r"when was (.+)\??$",
    ]
    for pat in patterns:
        m = re.search(pat, lower, re.I)
        if m:
            start, end = m.span(1)
            topic = _clean_topic(msg[start:end])
            if len(topic) >= 2:
                return topic
    if "?" in msg:
        return _clean_topic(msg.replace("?", ""))
    return _clean_topic(msg)


_CHITCHAT: dict[str, str] = {
    "hello": "Hello! Ask me anything — history, science, places, how things work.",
    "hi": "Hi there! What would you like to know?",
    "hey": "Hey! I'm here — try 'what is AI' or 'tell me about Paris'.",
    "thanks": "You're welcome!",
    "thank you": "You're welcome!",
    "how are you": "I'm ready to help. What can I look up for you?",
}


def _shorten(text: str, limit: int = 520) -> str:
    text = re.sub(r"\s+", " ", text.strip())
    if len(text) <= limit:
        return text
    cut = text[:limit]
    last = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
    if last > 120:
        return cut[: last + 1]
    return cut.rstrip() + "…"


def duckduckgo_answer(topic: str) -> str | None:
    q = urllib.parse.quote_plus(topic)
    data = _fetch_json(f"https://api.duckduckgo.com/?q={q}&format=json&no_html=1&skip_disambig=1")
    if not isinstance(data, dict):
        return None
    for key in ("AbstractText", "Answer", "Definition"):
        val = str(data.get(key, "")).strip()
        if len(val) > 20:
            src = str(data.get("AbstractSource", "")).strip()
            if src:
                return _shorten(f"{val} Source: {src}.")
            return _shorten(val)
    related = data.get("RelatedTopics") or []
    for item in related[:5]:
        if isinstance(item, dict) and item.get("Text"):
            return _shorten(str(item["Text"]))
    return None


def wikipedia_titles(topic: str, limit: int = 3) -> list[str]:
    q = urllib.parse.quote_plus(topic)
    data = _fetch_json(
        "https://en.wikipedia.org/w/api.php?"
        f"action=opensearch&search={q}&limit={limit}&namespace=0&format=json"
    )
    if not isinstance(data, list) or len(data) < 2:
        return []
    return [str(t) for t in (data[1] or []) if t]


def wikipedia_title(topic: str) -> str | None:
    titles = wikipedia_titles(topic, 1)
    return titles[0] if titles else None


def wikipedia_summary(title: str) -> str | None:
    slug = urllib.parse.quote(title.replace(" ", "_"), safe="")
    data = _fetch_json(f"https://en.wikipedia.org/api/rest_v1/page/summary/{slug}")
    if not isinstance(data, dict):
        return None
    extract = str(data.get("extract", "")).strip()
    if len(extract) < 30:
        return None
    desc = str(data.get("description", "")).strip()
    if desc:
        return _shorten(f"{desc}. {extract}")
    return _shorten(extract)


def _chitchat_reply(message: str) -> str | None:
    lower = message.strip().lower().rstrip("?.!")
    if lower in _CHITCHAT:
        return _CHITCHAT[lower]
    for key, reply in _CHITCHAT.items():
        if lower.startswith(key + " "):
            return reply
    if re.search(r"\bjoke\b", lower):
        ddg = duckduckgo_answer("short clean joke")
        if ddg and len(ddg) > 20:
            return _shorten(ddg, 280)
        return "Why did the browser need a break? Too many open tabs."
    return None


def _best_wiki_answer(topic: str, raw: str) -> str | None:
    seen: set[str] = set()
    for wq in _wiki_lookup_queries(topic, raw):
        for title in wikipedia_titles(wq, 3):
            key = title.lower()
            if key in seen:
                continue
            seen.add(key)
            summary = wikipedia_summary(title)
            if summary and len(summary) >= 40:
                return summary
    return None


def _followup_topic(message: str, history: str) -> str | None:
    lower = message.strip().lower()
    if not history:
        return None
    if re.match(r"^(tell me more|more about that|go on|continue|what else|and\?)$", lower):
        lines = [ln for ln in history.splitlines() if ln.startswith("User:")]
        if lines:
            last = lines[-1].replace("User:", "", 1).strip()
            return extract_topic(last) or last
    if re.match(r"^(what did i (?:just )?ask|repeat that|say that again|what was that)\??$", lower):
        lines = [ln for ln in history.splitlines() if ln.startswith("Assistant:")]
        if lines:
            return lines[-1].replace("Assistant:", "", 1).strip()[:400]
    if re.match(r"^(that|it|this)\??$", lower):
        lines = [ln for ln in history.splitlines() if ln.startswith("User:")]
        if lines:
            return extract_topic(lines[-1].replace("User:", "", 1)) or None
    return None


def answer_question(message: str, *, history: str = "") -> tuple[str, str | None]:
    """Return (spoken reply, optional URL — never required for voice)."""
    raw = message.strip().rstrip("?.!")
    chit = _chitchat_reply(message)
    if chit:
        return (chit, None)

    follow = _followup_topic(message, history)
    if follow and len(follow) > 3:
        if not follow.startswith(("User:", "Assistant:")):
            wiki = _best_wiki_answer(follow, follow)
            if wiki:
                return (wiki, None)
            ddg = duckduckgo_answer(follow)
            if ddg and _ddg_usable(ddg, follow):
                return (_shorten(ddg), None)
        return (_shorten(follow, 520), None)

    topic = extract_topic(message)
    if not topic or len(topic) < 2:
        return ("Could you rephrase that? Try 'what is AI' or 'tell me about Paris'.", None)

    queries: list[str] = []
    for q in (raw, topic):
        q = q.strip()
        if q and q.lower() not in {x.lower() for x in queries}:
            queries.append(q)

    for q in queries:
        key = q.lower()
        cached = _ANSWER_CACHE.get(key)
        if cached and time.time() - cached[0] < _CACHE_TTL_SEC:
            return cached[1]

    definitional = bool(re.search(r"^(what|who|tell me about|explain|define)\b", raw, re.I))
    explanatory = bool(re.search(r"^(why|how many|how much|how long|how old|how far|how)\b", raw, re.I))

    if explanatory:
        place = _place_from_question(raw)
        if place:
            title = wikipedia_title(place)
            if title:
                summary = wikipedia_summary(title)
                if summary and len(summary) >= 40:
                    result = (summary, None)
                    _store_cache(raw.lower(), result)
                    return result
        for q in queries:
            ddg = duckduckgo_answer(q)
            if ddg and _ddg_usable(ddg, q):
                result = (ddg, None)
                _store_cache(q.lower(), result)
                return result

    wiki = _best_wiki_answer(topic, raw)
    if wiki:
        result = (wiki, None)
        _store_cache(raw.lower(), result)
        return result

    for q in queries:
        ddg = duckduckgo_answer(q)
        if ddg and _ddg_usable(ddg, q):
            result = (ddg, None)
            _store_cache(q.lower(), result)
            return result

    wiki = _best_wiki_answer(topic, raw)
    if wiki:
        return (wiki, None)

    return (
        f"I searched Wikipedia and the web for {topic}, but nothing clear came up. "
        f"Try a more specific question, like 'what is {topic}' or 'tell me about {topic}'.",
        None,
    )


def _store_cache(key: str, value: tuple[str, str | None]) -> None:
    if len(_ANSWER_CACHE) >= _CACHE_MAX:
        oldest = min(_ANSWER_CACHE.items(), key=lambda kv: kv[1][0])[0]
        _ANSWER_CACHE.pop(oldest, None)
    _ANSWER_CACHE[key] = (time.time(), value)


def answer_from_page(body_text: str, question: str) -> str | None:
    """Simple extractive answer from visible page text — no cloud AI."""
    text = body_text.strip()
    if len(text) < 80:
        return None
    lower_q = question.lower()
    if not re.search(r"\b(this page|this site|this article|here|it say|on this)\b", lower_q):
        return None

    sentences = re.split(r"(?<=[.!?])\s+", text)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 35]
    if not sentences:
        return None

    keywords = [w for w in re.findall(r"[a-z]{4,}", lower_q) if w not in {
        "what", "does", "this", "page", "site", "about", "tell", "explain", "article", "here", "say",
    }]
    if keywords:
        scored = []
        for s in sentences[:80]:
            sl = s.lower()
            score = sum(1 for k in keywords if k in sl)
            if score:
                scored.append((score, s))
        if scored:
            scored.sort(key=lambda x: -x[0])
            picks = [s for _, s in scored[:3]]
            return _shorten(" ".join(picks), 500)

    return _shorten(" ".join(sentences[:3]), 500)


def summarize_extractive(text: str, max_bullets: int = 6) -> str:
    text = text.strip()
    if not text:
        return "No readable content on this page."
    sentences = re.split(r"(?<=[.!?])\s+", text)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 45]
    if not sentences:
        return text[:400] + ("…" if len(text) > 400 else "")
    # Prefer longer informative sentences from the start and middle
    picks: list[str] = []
    for s in sentences[:12]:
        if s not in picks:
            picks.append(s)
        if len(picks) >= max_bullets:
            break
    if len(picks) < 3 and len(sentences) > 12:
        mid = len(sentences) // 3
        for s in sentences[mid : mid + 4]:
            if s not in picks:
                picks.append(s)
            if len(picks) >= max_bullets:
                break
    return "• " + "\n• ".join(_shorten(p, 220) for p in picks[:max_bullets])
