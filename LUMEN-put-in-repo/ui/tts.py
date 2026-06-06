"""LUMEN Mind voice — instant local greeting (SAPI), Edge for replies only."""

from __future__ import annotations

import re
import sys
import tempfile
import threading
from datetime import datetime
from pathlib import Path
from typing import Callable

VOICE = "en-GB-RyanNeural"
RATE = "-12%"
PITCH = "-6Hz"
_CACHE_DIR = Path.home() / ".lumen" / "tts_cache"
_lock = threading.Lock()
_sapi_engine = None
_sapi_ready = threading.Event()
_greeting_active = False


def _tts_log(msg: str) -> None:
    try:
        p = Path.home() / ".lumen" / "tts.log"
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as f:
            f.write(f"{datetime.now():%H:%M:%S} {msg}\n")
    except OSError:
        pass


def prewarm_greeting(name: str) -> None:
    """Warm Windows SAPI on startup — no network, instant first greeting."""
    threading.Thread(target=_init_sapi, daemon=True, name="lumen-sapi-warm").start()


def ensure_greeting_ready(name: str) -> None:
    _init_sapi()


def speak(text: str, on_done: Callable[[], None] | None = None) -> None:
    threading.Thread(target=_speak_sync, args=(text, on_done), daemon=True).start()


def speak_reply(text: str, on_done: Callable[[], None] | None = None) -> None:
    clean = re.sub(r"[*#`_\[\]]", "", text or "").strip()
    clean = re.sub(r"\s+", " ", clean)
    if not clean:
        if on_done:
            on_done()
        return
    if len(clean) > 320:
        cut = clean[:320]
        last = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
        clean = cut[: last + 1] if last > 80 else cut + "…"
    speak(clean, on_done=on_done)


def speak_ack(on_done: Callable[[], None] | None = None) -> None:
    threading.Thread(target=_ack_sync, args=(on_done,), daemon=True).start()


def greet_user(name: str, on_done: Callable[[], None] | None = None) -> None:
    """Instant local greeting — never waits on network."""
    text = f"At your service, {name}."
    threading.Thread(
        target=_greet_instant,
        args=(text, on_done),
        daemon=True,
        name="lumen-greet",
    ).start()


def _init_sapi() -> None:
    global _sapi_engine
    if sys.platform != "win32":
        _sapi_ready.set()
        return
    try:
        import pyttsx3
        with _lock:
            if _sapi_engine is None:
                _sapi_engine = pyttsx3.init()
                for voice in _sapi_engine.getProperty("voices"):
                    vid = voice.id.lower()
                    vname = voice.name.lower()
                    if any(x in vid or x in vname for x in (
                        "david", "george", "mark", "ryan", "male", "hazel", "english",
                    )):
                        _sapi_engine.setProperty("voice", voice.id)
                        break
                _sapi_engine.setProperty("rate", 178)
                _tts_log("SAPI ready")
        _sapi_ready.set()
    except Exception as exc:
        _tts_log(f"SAPI init failed: {exc}")
        _sapi_ready.set()


def _greet_instant(text: str, on_done: Callable[[], None] | None) -> None:
    global _greeting_active
    _sapi_ready.wait(timeout=3.0)
    with _lock:
        if _greeting_active:
            if on_done:
                try:
                    on_done()
                except Exception:
                    pass
            return
        _greeting_active = True
    try:
        _speak_pyttsx3(text)
    finally:
        with _lock:
            _greeting_active = False
        if on_done:
            try:
                on_done()
            except Exception as exc:
                _tts_log(f"Greeting callback error: {exc}")


def _ack_sync(on_done: Callable[[], None] | None) -> None:
    try:
        _speak_pyttsx3("Go ahead.")
    finally:
        if on_done:
            try:
                on_done()
            except Exception:
                pass


def _speak_sync(text: str, on_done: Callable[[], None] | None = None) -> None:
    try:
        path = _synthesize_to_file(text)
        if path and _play_file(path):
            return
        _speak_pyttsx3(text)
    finally:
        if on_done:
            try:
                on_done()
            except Exception:
                pass


def _synthesize_to_file(text: str, cache_name: str | None = None) -> str | None:
    try:
        import asyncio
        import edge_tts
    except ImportError:
        return None

    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    if cache_name:
        out = _CACHE_DIR / cache_name
        if out.is_file() and out.stat().st_size > 500:
            return str(out)
    else:
        out = Path(tempfile.mktemp(suffix=".mp3"))

    async def _run() -> None:
        comm = edge_tts.Communicate(text, VOICE, rate=RATE, pitch=PITCH)
        await comm.save(str(out))

    try:
        import asyncio
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(_run())
        finally:
            loop.close()
        if out.is_file() and out.stat().st_size > 500:
            return str(out)
    except Exception as exc:
        _tts_log(f"Edge TTS failed: {exc}")
    return None


def _play_file(path: str) -> bool:
    try:
        import playsound3
        playsound3.playsound(path, block=True)
        return True
    except Exception:
        pass
    return False


def _speak_pyttsx3(text: str) -> bool:
    try:
        _init_sapi()
        with _lock:
            engine = _sapi_engine
            if engine is None:
                return False
            engine.say(text)
            engine.runAndWait()
        return True
    except Exception as exc:
        _tts_log(f"pyttsx3 failed: {exc}")
        return False
