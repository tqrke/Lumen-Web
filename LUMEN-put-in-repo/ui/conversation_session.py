"""Conversational context — follow-ups like Alexa/OpenJarvis ('play the second one')."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field


@dataclass
class ConversationSession:
    """Short-term session memory for multi-turn voice."""

    active: bool = False
    started_at: float = 0.0
    expires_at: float = 0.0
    last_user: str = ""
    last_reply: str = ""
    last_action: str = ""
    last_target: str = ""
    pending_prefix: str = ""
    turns: list[tuple[str, str]] = field(default_factory=list)

    CONVERSATION_SEC = 120.0

    def begin(self) -> None:
        now = time.time()
        self.active = True
        if not self.started_at:
            self.started_at = now
        self.expires_at = now + self.CONVERSATION_SEC

    def extend(self, seconds: float = CONVERSATION_SEC) -> None:
        if self.active:
            self.expires_at = time.time() + seconds

    def is_live(self) -> bool:
        return self.active and time.time() < self.expires_at

    def end(self) -> None:
        self.active = False
        self.started_at = 0.0
        self.expires_at = 0.0

    def record(self, user: str, reply: str, *, action: str = "", target: str = "") -> None:
        self.begin()
        self.last_user = user[:200]
        self.last_reply = reply[:300]
        if action:
            self.last_action = action
        if target:
            self.last_target = target
        self.turns.append((user[:120], reply[:160]))
        self.turns = self.turns[-8:]

    def context_hint(self) -> str:
        if not self.turns:
            return ""
        lines = []
        for u, a in self.turns[-3:]:
            lines.append(f"User: {u}")
            lines.append(f"Assistant: {a}")
        return "\n".join(lines)

    def expand_followup(self, text: str) -> str:
        """Turn vague follow-ups into concrete commands using session context."""
        from ui.command_sanitize import (
            combine_grocery_prefix,
            expand_scroll_command,
            expand_video_command,
            is_grocery_prefix_only,
        )

        t = text.strip()
        lower = t.lower()

        if self.pending_prefix:
            combined = combine_grocery_prefix(self.pending_prefix, t)
            if not is_grocery_prefix_only(combined):
                self.pending_prefix = ""
                return combined
            return combined

        expanded = expand_video_command(t)
        if expanded.lower() != lower:
            return expanded

        scroll_ctx = self.last_action == "scroll" or "scroll" in self.last_user.lower()
        scroll_fix = expand_scroll_command(t, scroll_context=scroll_ctx)
        if scroll_fix.lower() != lower:
            return scroll_fix
        if scroll_ctx and re.match(r"^up(?:\s+(?:a\s+)?(?:bit|little))?$", lower):
            return "scroll up"

        if re.match(r"^(search|add|put|get|buy)(?:\s+for)?$", self.last_user.lower()) and t:
            if not is_grocery_prefix_only(t) and not re.search(
                r"\b(?:the web|on google|online)\b", t, re.I
            ):
                combined = combine_grocery_prefix(self.last_user, t)
                if not is_grocery_prefix_only(combined):
                    return combined

        if re.search(r"\b(second|third|first|2nd|3rd|1st)\s+(one|video|result)\b", lower):
            return t

        if re.match(r"^(play|open|click|select|watch)\s+(it|that|the video|one)\s*$", lower):
            if "youtube" in self.last_target or "video" in self.last_action:
                if "second" in self.last_user.lower():
                    return "play the second video"
                if "first" in self.last_user.lower():
                    return "play the first video"
                return "play the first video"
            if self.last_target:
                return f"open {self.last_target}"

        if re.match(r"^(go back|back|mute|unmute|pause|play|stop|volume up|volume down)$", lower):
            return t

        if re.match(r"^(and|also|then)\s+", lower):
            return re.sub(r"^(and|also|then)\s+", "", t, flags=re.I)

        if lower in ("again", "repeat", "same thing", "do that again") and self.last_user:
            return self.last_user

        if re.match(r"^(tell me more|more about that|go on|continue|what else)$", lower) and self.last_user:
            return f"tell me more about {self.last_user}"

        if re.match(r"^(what did i ask|what did i just ask|repeat that|say that again)$", lower):
            return "what did I just ask"

        if re.match(r"^what about\s+", lower) and self.last_user:
            topic = re.sub(r"^what about\s+", "", t, flags=re.I)
            return f"tell me about {topic}"

        return t


_SESSION = ConversationSession()


def get_session() -> ConversationSession:
    return _SESSION
