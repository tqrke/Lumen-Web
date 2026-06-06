"""Offline-first speech-to-text for LUMEN Mind (Vosk + Google fallback)."""

from __future__ import annotations

import json
import re
import time
import threading
import urllib.request
import zipfile
from pathlib import Path

import numpy as np

STT_RATE = 16000
VOSK_MODEL_NAME = "vosk-model-small-en-us-0.15"
VOSK_MODEL_URL = f"https://alphacephei.com/vosk/models/{VOSK_MODEL_NAME}.zip"

# Restrict Vosk to likely everyday commands — much better than open vocabulary.
_COMMAND_GRAMMAR = json.dumps([
    "open youtube", "open google", "open gmail", "open maps", "open github",
    "open netflix", "open spotify", "open amazon", "open reddit", "open wikipedia",
    "open facebook", "open instagram", "open twitter", "open outlook", "open settings",
    "open tesco", "open sainsburys", "open asda", "open morrisons",
    "search", "search for",
    "search spaghetti", "search for spaghetti", "search spagetti", "search for spagetti",
    "search milk", "search bread", "search eggs", "search cheese",
    "search bananas", "search chicken", "search apples", "search butter", "search rice",
    "search pasta", "search tomatoes", "search potatoes", "search onions",
    "add to basket", "add to cart", "show basket", "view basket",
    "go to youtube", "go to google", "play music", "play the first video",
    "play the second video", "play the third video", "play the fourth video",
    "play the fifth video", "weather", "what's the weather", "search for",
    "read page", "read this page", "new tab", "go back", "close tab",
    "volume up", "volume down", "stop listening", "pause", "play", "mute", "unmute",
    "scroll up", "scroll up a bit", "scroll you", "nudge up", "up", "up a bit",
    "scroll down", "scroll",
    "start scrolling", "stop", "stop scrolling",
    "[unk]",
])

# Restrict Vosk to wake-like phrases — much better than open vocabulary for "Lumen".
_WAKE_GRAMMAR = json.dumps([
    "lumen", "hey lumen", "hi lumen", "ok lumen", "oi lumen",
    "loom in", "lu min", "lew man", "lewman", "lumin", "human",
    "lew min", "lou man", "hey lewman", "[unk]",
])

_model = None
_model_lock = threading.Lock()
_model_loading = False


def vosk_model_dir() -> Path:
    return Path.home() / ".lumen" / VOSK_MODEL_NAME


def vosk_available() -> bool:
    try:
        import vosk  # noqa: F401
        return vosk_model_dir().is_dir()
    except ImportError:
        return False


def ensure_vosk_model(log_fn=None) -> Path | None:
    """Download the small English Vosk model on first use (~40 MB)."""
    global _model_loading

    target = vosk_model_dir()
    if target.is_dir() and (target / "am").is_dir():
        return target

    with _model_lock:
        if target.is_dir() and (target / "am").is_dir():
            return target
        if _model_loading:
            return None
        _model_loading = True

    try:
        import vosk  # noqa: F401
    except ImportError:
        _model_loading = False
        return None

    target.parent.mkdir(parents=True, exist_ok=True)
    zip_path = target.parent / f"{VOSK_MODEL_NAME}.zip"

    try:
        if log_fn:
            log_fn("Downloading offline voice model (one-time, ~40 MB)...")
        urllib.request.urlretrieve(VOSK_MODEL_URL, zip_path)
        if log_fn:
            log_fn("Unpacking voice model...")
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(target.parent)
        try:
            zip_path.unlink()
        except OSError:
            pass
        if log_fn:
            log_fn("Offline voice model ready")
        return target if target.is_dir() else None
    except Exception as exc:
        if log_fn:
            log_fn(f"Vosk model download failed: {exc}")
        return None
    finally:
        _model_loading = False


def _get_vosk_model(log_fn=None):
    global _model

    model_path = ensure_vosk_model(log_fn)
    if not model_path:
        return None

    with _model_lock:
        if _model is not None:
            return _model
        try:
            from vosk import Model, SetLogLevel

            SetLogLevel(-1)
            _model = Model(str(model_path))
            return _model
        except Exception as exc:
            if log_fn:
                log_fn(f"Vosk init failed: {exc}")
            return None


def _resample(raw: bytes, src_rate: int, dst_rate: int) -> bytes:
    if src_rate == dst_rate or not raw:
        return raw
    a = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
    if a.size == 0:
        return raw
    n = max(int(a.size * dst_rate / src_rate), 1)
    x_old = np.linspace(0.0, 1.0, a.size)
    x_new = np.linspace(0.0, 1.0, n)
    return np.interp(x_new, x_old, a).astype(np.int16).tobytes()


def _normalize(raw: bytes, gain: float = 12000.0) -> bytes:
    a = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
    if a.size == 0:
        return raw
    peak = max(float(np.max(np.abs(a))), 1.0)
    a *= gain / peak
    return np.clip(a, -32767, 32767).astype(np.int16).tobytes()


def _trim_silence(raw: bytes, rate: int) -> bytes | None:
    a = np.frombuffer(raw, dtype=np.int16)
    if a.size == 0:
        return None
    win = max(int(rate * 0.02), 1)
    peak = float(np.max(np.abs(a))) or 1.0
    th = peak * 0.06
    start = 0
    for i in range(0, a.size - win, win):
        if float(np.mean(np.abs(a[i : i + win]))) > th:
            start = max(0, i - win)
            break
    end = a.size
    for i in range(a.size - win, 0, -win):
        if float(np.mean(np.abs(a[i : i + win]))) > th:
            end = min(a.size, i + win * 2)
            break
    if end <= start + win:
        return None
    return a[start:end].tobytes()


def audio_variants(raw: bytes, sample_rate: int) -> list[tuple[bytes, int]]:
    """Build PCM variants for STT backends."""
    out: list[tuple[bytes, int]] = []
    seen: set[int] = set()

    def add(data: bytes | None, rate: int) -> None:
        if not data:
            return
        key = hash(data[:80] + data[-80:] if len(data) > 160 else data)
        if key in seen:
            return
        seen.add(key)
        out.append((data, rate))

    for gain in (12000.0, 15000.0):
        pcm16 = _normalize(_resample(raw, sample_rate, STT_RATE), gain)
        add(pcm16, STT_RATE)

    trimmed = _trim_silence(raw, sample_rate)
    if trimmed and trimmed != raw:
        add(_normalize(_resample(trimmed, sample_rate, STT_RATE), 14000.0), STT_RATE)

    if sample_rate != STT_RATE:
        add(_normalize(raw, 12000.0), sample_rate)

    return out


def recognize_vosk(
    raw: bytes,
    sample_rate: int,
    log_fn=None,
    *,
    fast: bool = False,
    wake_grammar: bool = False,
    command_grammar: bool = False,
) -> str:
    model = _get_vosk_model(log_fn)
    if model is None:
        return ""

    try:
        from vosk import KaldiRecognizer
    except ImportError:
        return ""

    variants = audio_variants(raw, sample_rate)
    if fast:
        variants = variants[:2]

    for chunk, rate in variants:
        rec = KaldiRecognizer(model, rate)
        rec.SetWords(False)
        if wake_grammar:
            try:
                rec.SetGrammar(_WAKE_GRAMMAR)
            except Exception:
                pass
        elif command_grammar:
            try:
                rec.SetGrammar(_COMMAND_GRAMMAR)
            except Exception:
                pass
        rec.AcceptWaveform(chunk)
        result = json.loads(rec.FinalResult())
        text = str(result.get("text", "")).strip()
        if text and text != "[unk]":
            if log_fn:
                log_fn(f"Vosk STT: {text}")
            return text
    return ""


def recognize_google(recognizer, raw: bytes, sample_rate: int, log_fn=None) -> str:
    import speech_recognition as sr

    for idx, (chunk, rate) in enumerate(audio_variants(raw, sample_rate)):
        for lang in ("en-US", "en-GB"):
            audio = sr.AudioData(chunk, rate, 2)
            try:
                text = recognizer.recognize_google(audio, language=lang).strip()
                if text:
                    if log_fn:
                        log_fn(f"Google STT ({lang}) v{idx}: {text}")
                    return text
            except sr.UnknownValueError:
                continue
            except sr.RequestError as exc:
                if log_fn:
                    log_fn(f"Google STT error: {exc}")
                raise
    return ""


def _preprocess_pcm(raw: bytes) -> bytes:
    """Emphasis + gentle noise gate — clearer consonants for Vosk."""
    a = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
    if a.size < 4:
        return raw
    # Pre-emphasis (high-pass) helps wake word consonants
    emp = np.empty_like(a)
    emp[0] = a[0]
    emp[1:] = a[1:] - 0.96 * a[:-1]
    peak = max(float(np.max(np.abs(emp))), 1.0)
    gate = peak * 0.04
    emp[np.abs(emp) < gate] *= 0.15
    return np.clip(emp, -32767, 32767).astype(np.int16).tobytes()


def prepare_pcm(raw: bytes) -> bytes:
    """Fix clipped/shout audio before STT."""
    raw = _preprocess_pcm(raw)
    a = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
    if a.size == 0:
        return raw
    peak = max(float(np.max(np.abs(a))), 1.0)
    target = 14000.0
    if peak > 24000.0:
        target = 16000.0
    elif peak < 2500.0:
        target = 15000.0
    a *= target / peak
    return np.clip(a, -32767, 32767).astype(np.int16).tobytes()


def recognize_command(
    raw: bytes,
    sample_rate: int,
    *,
    recognizer=None,
    log_fn=None,
    use_google: bool = True,
) -> str:
    """Command phrase — Vosk first for short media/nav, Google for longer phrases."""
    if not raw:
        return ""

    raw = prepare_pcm(raw)

    try:
        from ui.intent_engine import is_fast_command
    except ImportError:
        is_fast_command = None  # type: ignore[assignment]

    vosk_text = recognize_vosk(raw, sample_rate, log_fn, fast=True)
    if vosk_text and is_fast_command and is_fast_command(vosk_text):
        return vosk_text

    if recognizer is not None and use_google:
        try:
            import speech_recognition as sr

            pcm16 = _normalize(_resample(raw, sample_rate, STT_RATE), 14000.0)
            for lang in ("en-US", "en-GB"):
                audio = sr.AudioData(pcm16, STT_RATE, 2)
                try:
                    text = recognizer.recognize_google(audio, language=lang).strip()
                    if text:
                        if log_fn:
                            log_fn(f"Google STT ({lang}): {text}")
                        return text
                except sr.UnknownValueError:
                    continue
                except sr.RequestError as exc:
                    if log_fn:
                        log_fn(f"Command Google error: {exc}")
                    break
        except Exception as exc:
            if log_fn:
                log_fn(f"Command Google error: {exc}")

    if vosk_text:
        return vosk_text
    return recognize_vosk(raw, sample_rate, log_fn, fast=False)


def _norm_words(text: str) -> set[str]:
    import re
    return set(re.findall(r"[a-z0-9']+", text.lower()))


def _agreement(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    wa, wb = _norm_words(a), _norm_words(b)
    if not wa or not wb:
        return 0.0
    overlap = len(wa & wb)
    return overlap / max(len(wa), len(wb))


def recognize_batch_command(
    raw: bytes,
    sample_rate: int,
    *,
    log_fn=None,
    hint: str = "",
) -> "SpeechResult":
    """Alexa-style — Google STT on full utterance; returns what you actually said."""
    from ui.speech_result import SpeechResult
    from ui.wake_words import normalize_command

    if not raw:
        return SpeechResult("", 0.0, "none")

    pcm = prepare_pcm(raw)
    dur = len(pcm) / 2 / max(sample_rate, 1)
    if dur < 0.2:
        return SpeechResult("", 0.0, "short")

    google_text = _google_batch(pcm, sample_rate, log_fn)

    if google_text:
        text = normalize_command(google_text.strip())
        if log_fn:
            log_fn(f"Heard (Google): {text!r}")
        return SpeechResult(text, 0.94, "google")

    # Offline fallback only when Google unavailable
    vosk_text = recognize_vosk(pcm, sample_rate, log_fn, fast=False).strip()
    if vosk_text:
        text = normalize_command(vosk_text)
        if log_fn:
            log_fn(f"Heard (Vosk fallback): {text!r}")
        return SpeechResult(text, 0.68, "vosk")

    if hint and len(hint.strip()) > 2:
        text = normalize_command(hint.strip())
        if log_fn:
            log_fn(f"Heard (hint fallback): {text!r}")
        from ui.command_sanitize import looks_like_question
        conf = 0.72 if looks_like_question(text) else 0.55
        return SpeechResult(text, conf, "hint")

    if log_fn:
        log_fn("STT: could not understand audio")
    return SpeechResult("", 0.0, "none")


def _google_batch(raw: bytes, sample_rate: int, log_fn=None) -> str:
    """Try Google with multiple gain variants — best-effort Alexa accuracy."""
    try:
        import speech_recognition as sr
    except ImportError:
        if log_fn:
            log_fn("Google STT unavailable (speech_recognition missing)")
        return ""

    rec = sr.Recognizer()
    rec.dynamic_energy_threshold = False
    rec.energy_threshold = 200
    rec.pause_threshold = 0.6

    for idx, (chunk, rate) in enumerate(audio_variants(raw, sample_rate)[:5]):
        pcm16 = _normalize(_resample(chunk, rate, STT_RATE), 13000.0 + idx * 800.0)
        audio = sr.AudioData(pcm16, STT_RATE, 2)
        for lang in ("en-GB", "en-US"):
            try:
                text = rec.recognize_google(audio, language=lang).strip()
                if text and text.lower() not in ("uh", "um", "hmm"):
                    if log_fn:
                        log_fn(f"Google STT ({lang}, v{idx}): {text}")
                    return text
            except sr.UnknownValueError:
                continue
            except sr.RequestError as exc:
                if log_fn:
                    log_fn(f"Google STT error: {exc}")
                return ""
            except Exception as exc:
                if log_fn:
                    log_fn(f"Google STT error: {exc}")
                continue
    return ""


def recognize_wake(
    raw: bytes,
    sample_rate: int,
    *,
    recognizer=None,
    log_fn=None,
) -> str:
    """Wake phrase — Vosk first, Google fallback on short clips."""
    if not raw:
        return ""

    raw = prepare_pcm(raw)
    dur = len(raw) / 2 / sample_rate
    trimmed = _trim_silence(raw, sample_rate) or raw
    if len(trimmed) / 2 / sample_rate > 2.5:
        trimmed = trimmed[-int(2.5 * sample_rate * 2) :]

    for gain in (15000.0, 18000.0):
        boosted = _normalize(_resample(trimmed, sample_rate, STT_RATE), gain)
        text = recognize_vosk(boosted, STT_RATE, log_fn, fast=True, wake_grammar=True)
        if text:
            return text

    if recognizer is not None and dur <= 3.0:
        import speech_recognition as sr

        pcm16 = _normalize(_resample(raw, sample_rate, STT_RATE), 15000.0)
        for lang in ("en-GB", "en-US"):
            audio = sr.AudioData(pcm16, STT_RATE, 2)
            try:
                text = recognizer.recognize_google(audio, language=lang).strip()
                if text:
                    if log_fn:
                        log_fn(f"Wake Google ({lang}): {text}")
                    return text
            except sr.UnknownValueError:
                continue
            except sr.RequestError as exc:
                if log_fn:
                    log_fn(f"Wake Google error: {exc}")
                break
    return ""


def recognize(
    raw: bytes,
    sample_rate: int,
    *,
    recognizer=None,
    log_fn=None,
    fast: bool = False,
) -> str:
    """Recognize speech — Vosk offline first, Google online fallback."""
    if not raw:
        return ""

    raw = prepare_pcm(raw)

    text = recognize_vosk(raw, sample_rate, log_fn, fast=fast)
    if text:
        return text

    if recognizer is not None:
        try:
            variants = audio_variants(raw, sample_rate)
            if fast:
                variants = variants[:2]
            import speech_recognition as sr
            for chunk, rate in variants:
                for lang in ("en-US", "en-GB"):
                    audio = sr.AudioData(chunk, rate, 2)
                    try:
                        text = recognizer.recognize_google(audio, language=lang).strip()
                        if text:
                            if log_fn:
                                log_fn(f"Google STT ({lang}): {text}")
                            return text
                    except sr.UnknownValueError:
                        continue
                    except sr.RequestError:
                        raise
        except Exception:
            return ""
    return ""


class StreamingRecognizer:
    """Continuous Vosk — live preview only; execution uses batch recognition."""

    _CHUNK = 1600
    _PARTIAL_STABLE_SEC = 0.55
    _PARTIAL_MIN_CHARS = 3

    def __init__(self, sample_rate: int, log_fn=None):
        self._src_rate = sample_rate
        self._log = log_fn
        self._buf = b""
        self._rec = None
        self._partial = ""
        self._partial_at = 0.0
        self._confirmed = ""
        self._segments: list[str] = []
        self._last_preview = ""
        self._pending_final = ""
        self._last_final_at = 0.0
        self._init_rec()

    def preview(self) -> str:
        """Live transcript — current utterance segments + partial."""
        base = " ".join(self._segments).strip()
        if self._partial:
            return f"{base} {self._partial}".strip() if base else self._partial.strip()
        return base

    def live_text(self) -> str:
        """Recent words only — avoids showing a long chain of misheard fragments."""
        if self._partial.strip() and self._partial.strip() != "[unk]":
            return self._partial.strip()
        if self._segments:
            return self._segments[-1]
        return ""

    def recent_phrase(self, *, max_segments: int = 2) -> str:
        """Last few finals + partial — for command hints."""
        parts = self._segments[-max_segments:] if self._segments else []
        if self._partial.strip() and self._partial.strip() != "[unk]":
            p = self._partial.strip()
            if not parts or parts[-1].lower() != p.lower():
                parts = list(parts) + [p]
        return " ".join(parts).strip()

    def take_pending_final(self) -> str:
        """Return latest stream final once (for immediate command execution)."""
        text = self._pending_final.strip()
        self._pending_final = ""
        return text

    def phrase_on_silence(self) -> str:
        """Full utterance when the user pauses."""
        if self._partial:
            p = self._partial.strip()
            if p and p != "[unk]":
                parts = list(self._segments)
                if not parts or parts[-1].lower() != p.lower():
                    parts.append(p)
                return " ".join(parts).strip()
        return " ".join(self._segments).strip()

    def is_partial_stable(self, stable_sec: float) -> bool:
        """True when live partial text has not changed — user likely finished."""
        p = self._partial.strip()
        if len(p) < 2 or p == "[unk]":
            return False
        return time.time() - self._partial_at >= stable_sec

    def segments_stable(self, stable_sec: float) -> bool:
        """True when last final segment is old and no new partial — pause after phrase."""
        if self._partial.strip():
            return False
        if not self._segments:
            return False
        return time.time() - self._last_final_at >= stable_sec

    def clear_utterance(self) -> None:
        self._segments.clear()
        self._confirmed = ""
        self._partial = ""
        self._partial_at = 0.0
        self._pending_final = ""

    def has_voice_activity(self) -> bool:
        """Brief pulse after a final — do not block silence on old partials."""
        if self._pending_final and time.time() - self._last_final_at < 0.35:
            return True
        return False

    def _init_rec(self) -> None:
        self._buf = b""
        self._partial = ""
        self._partial_at = 0.0
        self._confirmed = ""
        self._segments: list[str] = []
        self._last_preview = ""
        self._pending_final = ""
        self._last_final_at = 0.0
        model = _get_vosk_model(self._log)
        if not model:
            self._rec = None
            return
        try:
            from vosk import KaldiRecognizer

            self._rec = KaldiRecognizer(model, STT_RATE)
            self._rec.SetWords(False)
            # Open vocabulary — grammar mangled free speech and questions.
        except Exception as exc:
            if self._log:
                self._log(f"Stream rec init failed: {exc}")
            self._rec = None

    def reset(self) -> None:
        self._init_rec()

    def _pcm(self, block: np.ndarray) -> bytes:
        return _normalize(
            _resample(block.astype(np.int16).tobytes(), self._src_rate, STT_RATE),
            15000.0,
        )

    def _take_text(self, text: str, *, partial: bool = False, final: bool = False) -> str | None:
        text = text.strip()
        if not text or text == "[unk]":
            return None
        if final:
            if not self._segments or self._segments[-1].lower() != text.lower():
                self._segments.append(text)
            self._confirmed = " ".join(self._segments)
            self._partial = ""
            self._partial_at = 0.0
            self._pending_final = text
            self._last_final_at = time.time()
        if self._log and final:
            self._log(f"Stream preview (final): {text}")
        return text if final else None

    def flush_partial(self) -> str | None:
        return None

    def feed(self, block: np.ndarray, *, speech_active: bool = True) -> str | None:
        if self._rec is None or block.size == 0:
            return None

        pcm = _preprocess_pcm(block.astype(np.int16).tobytes())
        self._buf += _normalize(
            _resample(pcm, self._src_rate, STT_RATE),
            15000.0,
        )

        while len(self._buf) >= self._CHUNK:
            chunk = self._buf[: self._CHUNK]
            self._buf = self._buf[self._CHUNK :]
            if self._rec.AcceptWaveform(chunk):
                text = str(json.loads(self._rec.Result()).get("text", "")).strip()
                out = self._take_text(text, final=True)
                if out:
                    return out
            else:
                partial = str(json.loads(self._rec.PartialResult()).get("partial", "")).strip()
                if partial and partial != self._partial:
                    self._partial = partial
                    self._partial_at = time.time()

        return None


class GrammarHintRecognizer:
    """Grammar-constrained Vosk — accurate hints for open youtube, play second video, etc."""

    _CHUNK = 1600

    def __init__(self, sample_rate: int, log_fn=None):
        self._src_rate = sample_rate
        self._log = log_fn
        self._buf = b""
        self._rec = None
        self._segments: list[str] = []
        self._init_rec()

    def hint(self) -> str:
        return " ".join(self._segments).strip()

    def clear(self) -> None:
        self._segments.clear()

    def reset(self) -> None:
        self._init_rec()

    def _init_rec(self) -> None:
        self._buf = b""
        self._segments = []
        model = _get_vosk_model(self._log)
        if not model:
            self._rec = None
            return
        try:
            from vosk import KaldiRecognizer

            self._rec = KaldiRecognizer(model, STT_RATE)
            self._rec.SetWords(False)
            self._rec.SetGrammar(_COMMAND_GRAMMAR)
        except Exception as exc:
            if self._log:
                self._log(f"Grammar hint init failed: {exc}")
            self._rec = None

    def feed(self, block: np.ndarray) -> str | None:
        if self._rec is None or block.size == 0:
            return None

        pcm = _preprocess_pcm(block.astype(np.int16).tobytes())
        self._buf += _normalize(
            _resample(pcm, self._src_rate, STT_RATE),
            15000.0,
        )

        while len(self._buf) >= self._CHUNK:
            chunk = self._buf[: self._CHUNK]
            self._buf = self._buf[self._CHUNK :]
            if self._rec.AcceptWaveform(chunk):
                text = str(json.loads(self._rec.Result()).get("text", "")).strip()
                if text and text != "[unk]":
                    if not self._segments or self._segments[-1].lower() != text.lower():
                        self._segments.append(text)
                    if self._log:
                        self._log(f"Grammar hint (final): {text}")
                    return text
        return None


class StreamingWakeListener:
    """Feed mic blocks continuously; fires when Vosk hears the wake word."""

    _CHUNK = 960
    _COOLDOWN_SEC = 2.0

    def __init__(self, sample_rate: int, wake_check, log_fn=None):
        self._src_rate = sample_rate
        self._wake_check = wake_check
        self._log = log_fn
        self._buf = b""
        self._rec = None
        self._last_hit = 0.0
        self._init_rec()

    def _init_rec(self) -> None:
        self._buf = b""
        model = _get_vosk_model(self._log)
        if not model:
            self._rec = None
            return
        try:
            from vosk import KaldiRecognizer

            self._rec = KaldiRecognizer(model, STT_RATE)
            self._rec.SetWords(False)
            try:
                self._rec.SetGrammar(_WAKE_GRAMMAR)
            except Exception:
                pass
        except Exception:
            self._rec = None

    def reset(self) -> None:
        self._last_hit = 0.0
        self._init_rec()

    def feed(self, block: np.ndarray) -> str | None:
        if self._rec is None or block.size == 0:
            return None

        pcm = _normalize(
            _resample(block.astype(np.int16).tobytes(), self._src_rate, STT_RATE),
            15000.0,
        )
        self._buf += pcm

        while len(self._buf) >= self._CHUNK:
            chunk = self._buf[: self._CHUNK]
            self._buf = self._buf[self._CHUNK :]
            text = ""
            if self._rec.AcceptWaveform(chunk):
                text = str(json.loads(self._rec.Result()).get("text", "")).strip()
            else:
                text = str(json.loads(self._rec.PartialResult()).get("partial", "")).strip()
            if text and self._wake_check(text):
                now = time.time()
                if now - self._last_hit < self._COOLDOWN_SEC:
                    return None
                self._last_hit = now
                if self._log:
                    self._log(f"Stream wake: {text}")
                return text
        return None


def compact_alpha(text: str) -> str:
    return re.sub(r"[^a-z]", "", text.lower())
