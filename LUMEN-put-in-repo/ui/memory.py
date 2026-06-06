"""Persistent memory for LUMEN Mind — unlimited conversation history on disk."""

from __future__ import annotations

import json
import re
import threading
import time
from pathlib import Path


class MemoryStore:
    """Local-first memory — full history kept; context windows are bounded for speed."""

    _SAVE_DELAY_SEC = 0.75
    _MAX_STORED_TURNS = 5000
    _MAX_FACTS = 500
    _MAX_SHORTCUTS = 64
    _CONTEXT_CHAR_BUDGET = 9000

    def __init__(self, path: Path | None = None):
        self._path = path or Path.home() / ".lumen" / "memory.json"
        self._data: dict = {
            "user_name": "Josh",
            "facts": [],
            "turns": [],
            "preferences": {},
            "shortcuts": {},
            "routines": [],
        }
        self._save_timer: threading.Timer | None = None
        self._save_lock = threading.Lock()
        self._fact_index: dict[str, list[int]] = {}
        self.load()

    def load(self) -> None:
        try:
            if self._path.is_file():
                raw = json.loads(self._path.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    self._data.update(raw)
        except (json.JSONDecodeError, OSError):
            pass
        self._rebuild_index()

    def _rebuild_index(self) -> None:
        self._fact_index.clear()
        for i, fact in enumerate(self._data.get("facts", [])):
            for word in str(fact).lower().split():
                if len(word) >= 4:
                    self._fact_index.setdefault(word, []).append(i)

    def _flush_save(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(json.dumps(self._data, indent=2), encoding="utf-8")
        except OSError:
            pass

    def save(self) -> None:
        with self._save_lock:
            if self._save_timer:
                self._save_timer.cancel()
            self._save_timer = threading.Timer(self._SAVE_DELAY_SEC, self._flush_save)
            self._save_timer.daemon = True
            self._save_timer.start()

    def flush(self) -> None:
        with self._save_lock:
            if self._save_timer:
                self._save_timer.cancel()
                self._save_timer = None
        self._flush_save()

    def set_user_name(self, name: str) -> None:
        name = (name or "Josh").strip()[:40] or "Josh"
        self._data["user_name"] = name
        self.save()

    @property
    def user_name(self) -> str:
        return str(self._data.get("user_name", "Josh"))

    @property
    def turn_count(self) -> int:
        return len(self._data.get("turns", []))

    def set_preference(self, key: str, value: str) -> None:
        prefs = dict(self._data.get("preferences", {}))
        prefs[key[:40]] = str(value)[:200]
        self._data["preferences"] = prefs
        self.save()

    def get_preference(self, key: str, default: str = "") -> str:
        return str(self._data.get("preferences", {}).get(key, default))

    def add_shortcut(self, phrase: str, action: str) -> None:
        shortcuts = dict(self._data.get("shortcuts", {}))
        shortcuts[phrase.lower().strip()[:80]] = action[:200]
        if len(shortcuts) > self._MAX_SHORTCUTS:
            shortcuts = dict(list(shortcuts.items())[-self._MAX_SHORTCUTS :])
        self._data["shortcuts"] = shortcuts
        self.save()

    def match_shortcut(self, text: str) -> str | None:
        key = text.lower().strip()
        return self._data.get("shortcuts", {}).get(key)

    def _extract_facts(self, user: str) -> None:
        """Remember things the user explicitly shares."""
        u = user.strip()
        if not u:
            return
        lower = u.lower()
        patterns = [
            r"(?:my name is|call me|i am|i'm)\s+([a-z][a-z\s'-]{1,30})",
            r"(?:i live in|i'm from|i am from)\s+(.{2,60})",
            r"(?:remember(?: that)?|don't forget(?: that)?)\s+(.{4,120})",
            r"(?:i like|i love|i prefer|my favorite)\s+(.{2,80})",
        ]
        for pat in patterns:
            m = re.search(pat, lower, re.I)
            if m:
                fact = m.group(0).strip().rstrip(".")
                self.remember_fact(fact[:200])

    def add_turn(self, user: str, assistant: str) -> None:
        self._extract_facts(user)
        turns = list(self._data.get("turns", []))
        turns.append({
            "user": user[:2000],
            "assistant": assistant[:4000],
            "ts": time.time(),
        })
        if len(turns) > self._MAX_STORED_TURNS:
            turns = turns[-self._MAX_STORED_TURNS :]
        self._data["turns"] = turns
        self.save()

    def recent_context(self, limit: int = 30) -> str:
        turns = self._data.get("turns", [])[-limit:]
        if not turns:
            return ""
        lines = []
        for t in turns:
            lines.append(f"User: {t.get('user', '')}")
            lines.append(f"Assistant: {t.get('assistant', '')}")
        return "\n".join(lines)

    def history_block(self, max_chars: int | None = None) -> str:
        """Recent conversation for follow-ups — as much as fits the budget."""
        budget = max_chars or self._CONTEXT_CHAR_BUDGET
        turns = self._data.get("turns", [])
        if not turns:
            return ""
        chunks: list[str] = []
        used = 0
        for t in reversed(turns):
            block = f"User: {t.get('user', '')}\nAssistant: {t.get('assistant', '')}"
            if used + len(block) > budget and chunks:
                break
            chunks.append(block)
            used += len(block)
        chunks.reverse()
        return "\n\n".join(chunks)

    def last_user_message(self) -> str:
        turns = self._data.get("turns", [])
        if not turns:
            return ""
        return str(turns[-1].get("user", "")).strip()

    def last_assistant_message(self) -> str:
        turns = self._data.get("turns", [])
        if not turns:
            return ""
        return str(turns[-1].get("assistant", "")).strip()

    def recent_chat_messages(self, limit: int = 40) -> list[dict[str, str]]:
        """Turn memory into message list for multi-turn chat."""
        out: list[dict[str, str]] = []
        for turn in self._data.get("turns", [])[-limit:]:
            user = str(turn.get("user", "")).strip()
            assistant = str(turn.get("assistant", "")).strip()
            if user:
                out.append({"role": "user", "content": user})
            if assistant:
                out.append({"role": "assistant", "content": assistant})
        return out

    def remember_fact(self, fact: str) -> None:
        fact = fact.strip()[:200]
        if not fact:
            return
        facts = list(self._data.get("facts", []))
        if fact not in facts:
            facts.append(fact)
            if len(facts) > self._MAX_FACTS:
                facts = facts[-self._MAX_FACTS :]
            self._data["facts"] = facts
            self._rebuild_index()
            self.save()

    def recall_facts(self, query: str, limit: int = 8) -> list[str]:
        words = [w for w in query.lower().split() if len(w) >= 4]
        if not words:
            return list(self._data.get("facts", []))[-limit:]
        scores: dict[int, int] = {}
        for w in words:
            for idx in self._fact_index.get(w, []):
                scores[idx] = scores.get(idx, 0) + 1
        facts = self._data.get("facts", [])
        ranked = sorted(scores.items(), key=lambda x: -x[1])
        return [facts[i] for i, _ in ranked[:limit] if i < len(facts)]

    def facts_block(self) -> str:
        facts = self._data.get("facts", [])
        if not facts:
            return ""
        return "Known about the user:\n- " + "\n- ".join(facts[-20:])

    def preferences_block(self) -> str:
        prefs = self._data.get("preferences", {})
        if not prefs:
            return ""
        lines = [f"{k}: {v}" for k, v in list(prefs.items())[-12:]]
        return "User preferences:\n- " + "\n- ".join(lines)
