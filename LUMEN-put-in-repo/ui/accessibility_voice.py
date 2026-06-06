"""Accessibility-focused voice feedback — clear spoken status for assistive users."""

from __future__ import annotations

import threading

from ui.tts import speak, speak_ack


def announce(text: str, *, enabled: bool = True, brief: bool = False) -> None:
    """Speak a short status update (non-blocking)."""
    if not enabled or not text:
        return
    clean = text.strip()[:200]
    if brief:
        speak_ack(on_done=None)
        return
    threading.Thread(target=lambda: speak(clean), daemon=True, name="lumen-a11y").start()


def confirm_question(heard: str) -> str:
    return f"I heard: {heard}. Is that correct? Say yes or no."


def parse_yes_no(text: str) -> bool | None:
    t = text.lower().strip()
    if t in ("yes", "yeah", "yep", "correct", "right", "that's right", "affirmative", "ok", "okay"):
        return True
    if t in ("no", "nope", "wrong", "incorrect", "cancel", "stop"):
        return False
    return None


def listening_phrase(continuous: bool) -> str:
    if continuous:
        return "I'm listening. You can speak your next command."
    return 'Say "Lumen" when you need me.'


def error_phrase(kind: str) -> str:
    return {
        "mic": "Microphone problem. Checking audio now.",
        "stt": "I didn't catch that. Please try again.",
        "busy": "One moment, still working on your last request.",
        "low_conf": "I'm not sure I understood. Please repeat that.",
    }.get(kind, "Something went wrong. Please try again.")
