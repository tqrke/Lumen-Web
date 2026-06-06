"""LUMEN Mind voice — production pipeline: wake, converse, batch-accurate commands."""

from __future__ import annotations

import queue
import re
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import numpy as np
from PyQt6.QtCore import QObject, QThread, pyqtSignal

from ui.command_router import is_fast_phrase, match_fast_command
from ui.command_sanitize import (
    expand_scroll_command,
    is_grocery_prefix_only,
    is_voice_garbage,
    light_transcript,
    looks_like_question,
    merge_scroll_phrase,
    sanitize_command,
    voice_transcript,
)
from ui.intent_engine import is_wake_only, is_fast_command
from ui.speech_result import SpeechResult
from ui.stt_engine import (
    GrammarHintRecognizer,
    StreamingRecognizer,
    StreamingWakeListener,
    ensure_vosk_model,
    recognize_batch_command,
    recognize_wake,
)
from ui.wake_words import (
    is_incomplete_phrase,
    is_lumen_phantom,
    is_meaningful_voice,
    is_tts_garbage,
    looks_like_command,
    matches_wake,
    normalize_command,
    strip_wake_text,
)

CONVERSATION_SEC = 120.0
CMD_IDLE_SEC = 18.0
TTS_MUTE_SEC = 0.9
REPLY_MUTE_SEC = 0.5
WAKE_LOCK_SEC = 2.0
GREET_LOCK_SEC = 3.0
EXEC_DEDUPE_SEC = 2.5
_QUESTION_START = re.compile(
    r"^(what|who|why|how|when|where|which|tell me|explain|describe|can you|could you|"
    r"please|help me|what's|whats|is there|are there|talk about|chat about)\b",
    re.I,
)
MAX_AMBIENT = 7.0
MAX_THRESHOLD = 7.0
MIN_THRESHOLD = 1.5
CMD_SENSITIVE_FACTOR = 0.42
COMMIT_DELAY_SEC = 0.32
COMMIT_DELAY_GRAMMAR = 0.26
END_SPEECH_GAP_SEC = 0.38
QUESTION_GAP_SEC = 0.58
PARTIAL_STABLE_SEC = 0.42
QUESTION_STABLE_SEC = 0.62
MAX_TURN_SEC = 12.0
QUESTION_MAX_TURN_SEC = 18.0
MAX_TURN_BLOCKS = 180
MIN_RAW_BYTES = 28000
COMMIT_COOLDOWN_SEC = 0.55
COMMIT_COOLDOWN_FAIL_SEC = 0.15
COMMIT_COOLDOWN_OK_SEC = 1.1
WAKE_GRACE_SEC = 0.75

_FRAGMENT_ONLY = frozenset({
    "open", "you", "the", "a", "an", "hope", "pause", "play", "go", "to", "in", "on",
    "put", "it", "and", "so", "at", "of", "for", "is", "that", "your", "shoe",
})

_NOISE_FRAGMENTS = frozenset({
    "whoa", "woah", "uh", "um", "hmm", "hm", "and", "the", "a", "an",
    "you", "choose", "chew", "to", "it", "so", "ok", "okay",
})


def _is_noise_fragment(text: str) -> bool:
    words = re.sub(r"[^\w\s']", " ", text.lower()).split()
    if not words:
        return True
    return all(w in _NOISE_FRAGMENTS for w in words)


MIN_SPEECH_BLOCKS = 2
SILENCE_BLOCKS = 5
UTTERANCE_PAUSE_SEC = 0.55
MIN_CONFIDENCE = 0.55
MIN_CONFIDENCE_FAST = 0.48
MIN_CONFIDENCE_GOOGLE = 0.50
CONFIRM_BELOW = 0.76
_MIC_LEVEL_INTERVAL = 0.06
_PREVIEW_INTERVAL = 0.07
_STT_POOL = ThreadPoolExecutor(max_workers=1, thread_name_prefix="lumen-stt")


def _log(msg: str) -> None:
    try:
        p = Path.home() / ".lumen" / "voice.log"
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as f:
            f.write(f"{datetime.now():%H:%M:%S} {msg}\n")
    except OSError:
        pass


def _block_energy(block: np.ndarray) -> float:
    if block.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(block.astype(np.float64) ** 2)))


def _has_wake(text: str) -> bool:
    return matches_wake(text)


def _strip_wake(text: str) -> str:
    return sanitize_command(strip_wake_text(text))


class LiveMic:
    """Stable mic capture — capped ambient floor prevents deafness."""

    def __init__(self):
        import sounddevice as sd

        info = sd.query_devices(kind="input")
        idx = info.get("index")
        dev = sd.query_devices(idx, kind="input")
        self.rate = min(int(dev.get("default_samplerate", 16000) or 16000), 48000)
        self.device_name = str(dev.get("name", "?"))
        self.block = max(int(self.rate * 0.025), 256)
        self._q: queue.Queue[tuple[float, np.ndarray]] = queue.Queue(maxsize=300)
        self._running = True
        self._floor = 2.5
        self._peak = 8.0
        self._errors = 0
        self._stream = sd.InputStream(
            samplerate=self.rate,
            channels=1,
            dtype="int16",
            blocksize=self.block,
            device=idx,
            callback=self._on_audio,
        )
        self._stream.start()
        time.sleep(0.12)
        self._calibrate()
        _log(
            f"Mic {self.device_name} rate={self.rate} "
            f"floor={self._floor:.1f} th={self.threshold():.1f}"
        )

    def _on_audio(self, indata, frames, time_info, status) -> None:
        if not self._running:
            return
        if status:
            self._errors += 1
        block = indata[:, 0].copy()
        energy = _block_energy(block)
        try:
            self._q.put_nowait((energy, block))
        except queue.Full:
            try:
                self._q.get_nowait()
            except queue.Empty:
                pass
            try:
                self._q.put_nowait((energy, block))
            except queue.Full:
                pass

    def _calibrate(self) -> None:
        samples: list[float] = []
        end = time.time() + 0.5
        while time.time() < end:
            try:
                e, _ = self._q.get(timeout=0.03)
                samples.append(e)
            except queue.Empty:
                continue
        if samples:
            samples.sort()
            self._floor = min(max(samples[len(samples) // 4], 1.4), MAX_AMBIENT)
            self._peak = min(max(samples[-1], self._floor * 1.6), 35.0)

    def threshold(self, *, sensitive: bool = False) -> float:
        th = max(min(self._floor * 1.32, MAX_AMBIENT * 1.05), MIN_THRESHOLD)
        th = min(th, MAX_THRESHOLD)
        if sensitive:
            th *= CMD_SENSITIVE_FACTOR
        return th

    def note(self, energy: float) -> None:
        if energy < self._floor * 0.85:
            self._floor = self._floor * 0.992 + energy * 0.008
        self._floor = min(max(self._floor, 1.2), MAX_AMBIENT)
        if energy > self._peak:
            self._peak = energy * 0.25 + self._peak * 0.75

    def is_speech(self, energy: float, *, sensitive: bool = False) -> bool:
        th = self.threshold(sensitive=sensitive)
        # Stay above ambient — gaming mics sit near floor and never "stop speaking" otherwise.
        min_above_floor = self._floor * (1.14 if sensitive else 1.22)
        return energy > max(th, min_above_floor)

    def read(self, timeout: float = 0.03) -> tuple[float, np.ndarray] | None:
        try:
            return self._q.get(timeout=timeout)
        except queue.Empty:
            return None

    def restart(self) -> bool:
        """Recover stalled mic stream without restarting the app."""
        import sounddevice as sd

        try:
            self._stream.stop()
            self._stream.close()
        except Exception:
            pass
        try:
            idx = sd.query_devices(kind="input").get("index")
            self._stream = sd.InputStream(
                samplerate=self.rate,
                channels=1,
                dtype="int16",
                blocksize=self.block,
                device=idx,
                callback=self._on_audio,
            )
            self._stream.start()
            self._calibrate()
            self._errors = 0
            _log("Mic recovered")
            return True
        except Exception as exc:
            _log(f"Mic recovery failed: {exc}")
            return False

    def stop(self) -> None:
        self._running = False
        try:
            self._stream.stop()
            self._stream.close()
        except Exception:
            pass

    @staticmethod
    def join(blocks: list[np.ndarray]) -> bytes:
        if not blocks:
            return b""
        return np.concatenate(blocks, axis=0).astype(np.int16).tobytes()


class _VoiceWorker(QThread):
    wake = pyqtSignal(bool)
    command_listen = pyqtSignal()
    speech_started = pyqtSignal()
    transcript = pyqtSignal(str)
    status = pyqtSignal(str)
    error = pyqtSignal(str)
    mic_ready = pyqtSignal(bool)
    heard = pyqtSignal(str)
    mic_level = pyqtSignal(float)
    partial_text = pyqtSignal(str)
    mic_health = pyqtSignal(float, float)
    confidence = pyqtSignal(float)
    confirm_needed = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self._running = False
        self._mic: LiveMic | None = None
        self._stream_wake: StreamingWakeListener | None = None
        self._stream_cmd: StreamingRecognizer | None = None
        self._stream_grammar: GrammarHintRecognizer | None = None
        self._mode = "idle"
        self._manual = False
        self._lock = threading.Lock()
        self._conversation_until = 0.0
        self._ready_at = 0.0
        self._mute_until = 0.0
        self._wake_lock = 0.0
        self._greet_lock = 0.0
        self._queued = ""
        self._last_cmd = ""
        self._last_cmd_at = 0.0
        self._last_voice = 0.0
        self._speech_frames: list[np.ndarray] = []
        self._silent = 0
        self._speech_ui = False
        self._last_level_emit = 0.0
        self._last_preview_emit = 0.0
        self._last_preview = ""
        self._last_health_emit = 0.0
        self._idle_ticks = 0
        self._pending_confirm = ""
        self._confirm_enabled = True
        self._await_greeting = False
        self._greeting_deadline = 0.0
        self._utterance_due = 0.0
        self._in_turn = False
        self._turn_frames: list[np.ndarray] = []
        self._commit_at = 0.0
        self._turn_started_at = 0.0
        self._last_speech_at = 0.0
        self._turn_peak_energy = 0.0
        self._speech_seen_in_turn = False
        self._stt_busy = False
        self._assistant_busy = False
        self._commit_cooldown_until = 0.0
        self._wake_grace_until = 0.0
        self._last_commit_log = ""

    def set_assistant_busy(self, busy: bool) -> None:
        """Block new commits while the assistant is thinking or speaking."""
        with self._lock:
            self._assistant_busy = bool(busy)
            if busy:
                self._commit_at = 0.0
                self._turn_frames.clear()
                self._speech_frames.clear()
                self._in_turn = False
                self._silent = 0
                self._reset_turn_eou()
                self.status.emit("Answering…")
            else:
                self._commit_cooldown_until = time.time() + 0.35
                self._mute_until = time.time() + 0.12

    def is_assistant_busy(self) -> bool:
        return self._assistant_busy

    def stop(self) -> None:
        self._running = False
        if self._mic:
            self._mic.stop()
        self.wait(4000)

    def listen_command_now(self) -> None:
        with self._lock:
            self._manual = True

    def extend_conversation(self) -> None:
        self._conversation_until = time.time() + CONVERSATION_SEC
        if self._mode == "idle":
            self._open_conversation()

    def set_confirm_enabled(self, enabled: bool) -> None:
        self._confirm_enabled = bool(enabled)

    def greeting_finished(self) -> None:
        now = time.time()
        self._await_greeting = False
        self._greeting_deadline = 0.0
        self._ready_at = now + 0.03
        self._mute_until = now + 0.12
        if self._queued:
            cmd = self._queued
            self._queued = ""
            self._run_command(cmd, confidence=0.9, source="wake_combo")
        _log("Greeting done — listening")
        self.command_listen.emit()

    def notify_tts_start(self, *, greeting: bool = False) -> None:
        now = time.time()
        self._mute_until = now + (TTS_MUTE_SEC if greeting else REPLY_MUTE_SEC)
        if greeting:
            self._await_greeting = True
            self._greeting_deadline = now + 4.0
        self._ready_at = now + (0.08 if greeting else 0.05)

    def notify_tts_finished(self) -> None:
        self.resume_listening()

    def resume_listening(self) -> None:
        """Reset mic pipeline — ready for the next command immediately."""
        with self._lock:
            now = time.time()
            self._await_greeting = False
            self._greeting_deadline = 0.0
            self._mute_until = now + 0.08
            self._ready_at = now + 0.03
            self._conversation_until = now + CONVERSATION_SEC
            self._last_voice = now
            self._speech_frames.clear()
            self._silent = 0
            self._last_preview = ""
            self._commit_at = 0.0
            self._in_turn = False
            self._turn_frames.clear()
            self._reset_turn_eou()
            self._commit_cooldown_until = 0.0
            self._wake_grace_until = 0.0
            self._mode = "conversation"
            if self._stream_cmd:
                self._stream_cmd.reset()
            if self._stream_grammar:
                self._stream_grammar.reset()
            self.status.emit("Listening…")
            _log("Ready — next command")
        self.command_listen.emit()

    def _norm(self, text: str) -> str:
        return re.sub(r"\s+", " ", normalize_command(text).lower().strip())

    def _dup(self, text: str) -> bool:
        key = self._norm(text)
        return bool(key and key == self._norm(self._last_cmd)
                     and time.time() - self._last_cmd_at < EXEC_DEDUPE_SEC)

    def _open_conversation(self) -> None:
        self._mode = "conversation"
        now = time.time()
        self._conversation_until = now + CONVERSATION_SEC
        self._last_voice = now
        self._speech_frames.clear()
        self._turn_frames.clear()
        self._in_turn = False
        self._silent = 0
        self._reset_turn_eou()
        if self._stream_cmd:
            self._stream_cmd.reset()
        if self._stream_grammar:
            self._stream_grammar.reset()
        self.command_listen.emit()
        self.status.emit("Listening…")
        _log("Conversation ON")

    def _open_idle(self) -> None:
        self._mode = "idle"
        self._speech_frames.clear()
        self._silent = 0
        if self._mic:
            self._mic._calibrate()
        self.status.emit('Say "Lumen"')
        _log("Idle — say Lumen")

    def _trigger_wake(self, text: str) -> None:
        now = time.time()
        if now < self._wake_lock:
            return
        self._wake_lock = now + WAKE_LOCK_SEC
        self._greet_lock = now + GREET_LOCK_SEC
        self._speech_frames.clear()

        extra = _strip_wake(text)
        if extra and is_meaningful_voice(extra) and not is_incomplete_phrase(extra):
            self._queued = extra
        else:
            self._queued = ""

        if self._stream_wake:
            self._stream_wake.reset()

        self._open_conversation()
        self._ready_at = now + 0.05
        self._mute_until = now + 0.25
        self._wake_grace_until = now + WAKE_GRACE_SEC
        self._commit_cooldown_until = now + 0.25
        self.status.emit("At your service…")
        _log(f"WAKE: {text!r}")
        self.wake.emit(bool(self._queued))

    def _try_wake(self, raw: bytes) -> bool:
        if not raw:
            return False
        text = recognize_wake(raw, self._mic.rate, log_fn=_log)
        if text and _has_wake(text):
            self._trigger_wake(text)
            return True
        return False

    def _can_execute(self) -> bool:
        return time.time() >= self._ready_at and not self._assistant_busy

    def _should_process(self, text: str) -> bool:
        t = voice_transcript(text) or light_transcript(text)
        if not t or is_voice_garbage(t):
            return False
        if is_wake_only(t) or is_lumen_phantom(t) or is_tts_garbage(t):
            return False
        if match_fast_command(t) or match_fast_command(sanitize_command(t)):
            return True
        if looks_like_question(t) and len(t.split()) >= 2:
            return True
        if len(t) < 2:
            return False
        words = t.split()
        if len(words) == 1 and words[0].lower() in _FRAGMENT_ONLY:
            if match_fast_command(t) is None and not is_fast_phrase(sanitize_command(t)):
                return False
        if len(t) <= 2 and t.lower() not in ("go", "no", "ok", "up"):
            return False
        return True

    def _ensure_turn(self) -> None:
        if not self._in_turn:
            self._in_turn = True
            self._silent = 0
            self._turn_started_at = time.time()
            self._turn_peak_energy = 0.0
            self._speech_seen_in_turn = False

    def _begin_turn(self) -> None:
        if not self._in_turn:
            self._in_turn = True
            self._turn_frames.clear()
            self._silent = 0
            self._turn_started_at = time.time()
            self._turn_peak_energy = 0.0
            self._speech_seen_in_turn = False

    def _reset_turn_eou(self) -> None:
        self._commit_at = 0.0
        self._turn_started_at = 0.0
        self._last_speech_at = 0.0
        self._turn_peak_energy = 0.0
        self._speech_seen_in_turn = False

    def _is_turn_speech(self, energy: float) -> bool:
        """Detect user speech vs gaming-mic room noise during a command turn."""
        if not self._mic:
            return False
        floor = self._mic._floor
        base = max(floor * 1.20, self._mic.threshold(sensitive=False) * 0.9)
        if self._turn_peak_energy > base * 1.35:
            return energy > max(base, self._turn_peak_energy * 0.40)
        return energy > base

    def _note_turn_speech(self, energy: float) -> None:
        now = time.time()
        self._last_voice = now
        self._conversation_until = now + CONVERSATION_SEC
        if energy > self._turn_peak_energy:
            self._turn_peak_energy = energy
        # Only count as real speech if clearly above ambient (gaming-mic noise floor)
        if self._mic and energy >= self._mic._floor * 1.30:
            self._speech_seen_in_turn = True
            self._last_speech_at = now

    def _buffered_bytes(self) -> int:
        frames = self._turn_frames if len(self._turn_frames) >= MIN_SPEECH_BLOCKS else self._speech_frames
        if not frames:
            return 0
        return sum(getattr(f, "nbytes", 0) for f in frames)

    def _has_meaningful_utterance(self) -> bool:
        """Only commit when the recognizer actually heard words (not silence/noise)."""
        grammar = self._stream_grammar.hint() if self._stream_grammar else ""
        if grammar and not is_voice_garbage(grammar):
            return True
        live = self._live_transcript()
        if live and len(live.strip()) >= 3 and not is_voice_garbage(live):
            return True
        return False

    def _schedule_commit(self, delay: float, reason: str) -> None:
        if self._stt_busy or self._assistant_busy or time.time() < self._commit_cooldown_until:
            return
        if time.time() < self._wake_grace_until:
            return
        if not self._has_meaningful_utterance():
            return
        at = time.time() + max(delay, 0.12)
        if self._commit_at == 0.0 or at < self._commit_at:
            self._commit_at = at
            msg = f"End-of-speech ({reason}) in {delay:.2f}s"
            if msg != self._last_commit_log:
                self._last_commit_log = msg
                _log(msg)

    def _live_transcript(self) -> str:
        if not self._stream_cmd:
            return ""
        return self._stream_cmd.live_text() or self._stream_cmd.recent_phrase()

    def _preview_text(self) -> str:
        grammar = self._stream_grammar.hint() if self._stream_grammar else ""
        if grammar and not looks_like_question(grammar):
            cmd = sanitize_command(grammar)
            if match_fast_command(cmd) or is_fast_phrase(cmd):
                return cmd
        open_live = self._stream_cmd.live_text() if self._stream_cmd else ""
        if looks_like_question(open_live or grammar):
            return self._stream_cmd.preview() if self._stream_cmd else grammar
        if open_live:
            cmd = sanitize_command(open_live)
            if match_fast_command(cmd) or is_fast_phrase(cmd):
                return cmd
        if grammar:
            return sanitize_command(grammar)
        return sanitize_command(open_live) if open_live else ""

    def _utterance_is_question(self) -> bool:
        live = self._live_transcript()
        hint = self._stream_cmd.phrase_on_silence() if self._stream_cmd else ""
        return looks_like_question(live or hint)

    def _grammar_is_spurious(self, grammar_final: str) -> bool:
        """Grammar often hears 'youtube' / 'pause' inside longer questions."""
        live = self._live_transcript()
        if looks_like_question(live):
            return True
        if not live:
            return False
        g_words = grammar_final.lower().split()
        live_words = live.lower().split()
        if len(live_words) > len(g_words) + 2:
            return True
        if len(g_words) == 1 and g_words[0] in {"youtube", "google", "pause", "play", "weather"}:
            if len(live_words) >= 3:
                return True
        if g_words == ["scroll"]:
            live_l = live.lower()
            if re.search(r"scroll\s+(?:up|you|uo)\b", live_l) or live_l.strip() in ("up", "you", "uo"):
                return True
            if self._stream_cmd:
                preview = self._stream_cmd.preview().lower()
                partial = (self._stream_cmd._partial or "").strip().lower()
                if re.search(r"scroll\s+(?:up|you|uo)\b", preview):
                    return True
                if partial in ("up", "you", "uo") or partial.startswith("up "):
                    return True
        return False

    def _resolve_scroll_hint(self, hint: str, live: str = "") -> str:
        stream_phrase = self._stream_cmd.phrase_on_silence() if self._stream_cmd else ""
        partial = ""
        preview = ""
        if self._stream_cmd:
            partial = (self._stream_cmd._partial or "").strip()
            preview = self._stream_cmd.preview()
        merged = merge_scroll_phrase(hint, stream_phrase, live, preview, partial)
        return expand_scroll_command(merged)

    def _tick_end_of_utterance(self, energy: float, *, turn_speech: bool) -> None:
        """Commit when speech gap or stable partial — one utterance at a time."""
        if self._stt_busy or self._assistant_busy or time.time() < self._commit_cooldown_until:
            return
        if time.time() < self._wake_grace_until:
            return
        if not self._in_turn or not self._speech_seen_in_turn:
            return
        if self._commit_at:
            return
        now = time.time()
        gap = now - self._last_speech_at if self._last_speech_at else 0.0
        question = self._utterance_is_question()
        gap_needed = QUESTION_GAP_SEC if question else END_SPEECH_GAP_SEC
        stable_needed = QUESTION_STABLE_SEC if question else PARTIAL_STABLE_SEC
        max_turn = QUESTION_MAX_TURN_SEC if question else MAX_TURN_SEC

        live_hint = self._live_transcript()
        if live_hint:
            norm_live = voice_transcript(live_hint) or live_hint
            if is_incomplete_phrase(norm_live) or is_grocery_prefix_only(norm_live):
                gap_needed = max(gap_needed, 0.95)
                stable_needed = max(stable_needed, 0.82)
                max_turn = max(max_turn, 14.0)
            if norm_live.strip().lower() == "scroll":
                gap_needed = max(gap_needed, 0.72)
                stable_needed = max(stable_needed, 0.65)

        if self._turn_started_at and now - self._turn_started_at >= max_turn:
            self._schedule_commit(0.08, "max_length")
            return

        if not turn_speech and gap >= gap_needed:
            delay = 0.22 if question else 0.16
            self._schedule_commit(delay, "speech_gap")
            return

        if self._stream_cmd and self._stream_cmd.is_partial_stable(stable_needed):
            self._schedule_commit(0.20 if question else 0.18, "stable_partial")
            return

        if self._stream_cmd and self._stream_cmd.segments_stable(stable_needed):
            self._schedule_commit(0.20 if question else 0.18, "stable_text")

    def _utterance_hint(self) -> str:
        grammar = self._stream_grammar.hint() if self._stream_grammar else ""
        if grammar and not looks_like_question(grammar) and not is_voice_garbage(grammar):
            return sanitize_command(grammar)
        open_vocab = self._stream_cmd.recent_phrase() if self._stream_cmd else ""
        live = self._live_transcript()
        if looks_like_question(live or open_vocab):
            return open_vocab or live
        if open_vocab and not is_voice_garbage(open_vocab):
            cmd = sanitize_command(open_vocab)
            if match_fast_command(cmd) or is_fast_phrase(cmd):
                return cmd
        return grammar or open_vocab or live

    def _commit_turn(self) -> None:
        """Silence after speech → Google STT on full clip → act (one at a time)."""
        if self._stt_busy or self._assistant_busy:
            return
        if time.time() < self._commit_cooldown_until:
            self._commit_at = 0.0
            return
        if not self._can_execute():
            self._commit_at = time.time() + 0.12
            return

        self._commit_at = 0.0
        self._last_commit_log = ""

        frames = list(self._turn_frames)
        if len(frames) < MIN_SPEECH_BLOCKS and len(self._speech_frames) >= MIN_SPEECH_BLOCKS:
            frames = self._speech_frames[-MAX_TURN_BLOCKS:]
        if len(frames) < MIN_SPEECH_BLOCKS:
            self._turn_frames.clear()
            self._in_turn = False
            self._reset_turn_eou()
            return

        raw = LiveMic.join(frames)
        if len(raw) < MIN_RAW_BYTES:
            _log(f"Turn too short ({len(raw)} bytes)")
            self._turn_frames.clear()
            self._in_turn = False
            self._reset_turn_eou()
            return

        hint = self._utterance_hint()
        live = self._live_transcript()
        # No recognized words → it was silence/noise. Never transcribe empty clips.
        hint_ok = bool(hint) and not is_voice_garbage(hint)
        live_ok = bool(live) and len(live.strip()) >= 3 and not is_voice_garbage(live)
        if not hint_ok and not live_ok:
            self._turn_frames.clear()
            self._speech_frames.clear()
            self._in_turn = False
            self._reset_turn_eou()
            self._commit_cooldown_until = time.time() + 0.15
            return

        hint_cmd = sanitize_command(hint) if hint and not is_voice_garbage(hint) else ""
        if hint_cmd:
            hint_cmd = self._resolve_scroll_hint(hint_cmd, live)
            hint_cmd = sanitize_command(hint_cmd) if hint_cmd else ""
        if hint_cmd and match_fast_command(hint_cmd) and not looks_like_question(hint_cmd):
            self._in_turn = False
            self._turn_frames.clear()
            self._speech_frames.clear()
            self._silent = 0
            self._reset_turn_eou()
            self._stt_busy = True
            _log(f"Fast command: {hint_cmd!r}")
            self.status.emit("Processing…")
            understood = False
            try:
                if self._stream_cmd:
                    self._stream_cmd.reset()
                if self._stream_grammar:
                    self._stream_grammar.reset()
                understood = self._handle_text(SpeechResult(hint_cmd, 0.93, "grammar"))
            finally:
                self._stt_busy = False
                self._commit_cooldown_until = time.time() + (
                    COMMIT_COOLDOWN_OK_SEC if understood else COMMIT_COOLDOWN_FAIL_SEC
                )
            return

        self._in_turn = False
        self._turn_frames.clear()
        self._speech_frames.clear()
        self._silent = 0
        self._reset_turn_eou()

        self._stt_busy = True
        _log(f"Processing speech ({len(raw)} bytes, hint={hint!r})")
        self.status.emit("Processing…")
        understood = False
        try:
            result = self._batch_recognize(raw, hint=hint)
            if self._stream_cmd:
                self._stream_cmd.clear_utterance()
            if self._stream_grammar:
                self._stream_grammar.clear()

            text = voice_transcript(result.text) if result.text else ""
            if hint_cmd and match_fast_command(hint_cmd) and not looks_like_question(hint_cmd):
                text = hint_cmd
            elif not text and hint and not is_voice_garbage(hint):
                hinted = voice_transcript(hint)
                if hinted and not is_voice_garbage(hinted):
                    if looks_like_question(hinted) or match_fast_command(sanitize_command(hinted)):
                        text = hinted
                        result = SpeechResult(text, 0.82, "stream")
                        _log(f"Using stream hint: {text!r}")

            if not text or not self._should_process(text):
                _log(f"Not understood: {text!r} (source={result.source})")
                self.status.emit("Didn't catch that — try again")
                self.command_listen.emit()
            elif result.confidence < MIN_CONFIDENCE and result.source not in ("google", "stream", "hint"):
                _log(f"Skip (low conf {result.confidence:.2f}): {text!r}")
                self.status.emit("Listening…")
            else:
                understood = self._handle_text(
                    SpeechResult(text, max(result.confidence, 0.85), result.source),
                )
        finally:
            self._stt_busy = False
            self._commit_cooldown_until = time.time() + (
                COMMIT_COOLDOWN_OK_SEC if understood else COMMIT_COOLDOWN_FAIL_SEC
            )

    def _try_execute_utterance(self, phrase: str, *, confidence: float, source: str) -> bool:
        return False

    def _skip(self, text: str) -> bool:
        if not text or is_wake_only(text) or is_lumen_phantom(text) or is_tts_garbage(text):
            return True
        if time.time() < self._ready_at:
            _log(f"Skip (not ready): {text!r}")
            return True
        if time.time() < self._mute_until:
            t = text.lower()
            if any(x in t for x in (
                "at your service", "your service", "opening", "opened",
                "navigating", "blue moon", "blue moons", "thinking", "speaking",
            )):
                _log(f"Skip (echo): {text!r}")
                return True
        return False

    def _run_command(self, text: str, *, confidence: float, source: str) -> bool:
        text = voice_transcript(text)
        if self._skip(text) or not self._should_process(text):
            return False
        fast = (
            not looks_like_question(text)
            and (is_fast_phrase(sanitize_command(text)) or match_fast_command(text) is not None)
        )
        if source in ("google", "vosk", "hint", "wake_combo", "confirmed", "stream"):
            min_conf = MIN_CONFIDENCE_GOOGLE
        else:
            min_conf = MIN_CONFIDENCE_FAST if fast else MIN_CONFIDENCE
        if confidence < min_conf:
            _log(f"Skip (low conf {confidence:.2f}): {text!r}")
            return False
        if (
            self._confirm_enabled
            and not fast
            and source not in ("google", "vosk", "hint", "confirmed", "wake_combo")
            and confidence < CONFIRM_BELOW
            and "?" not in text
            and not _QUESTION_START.search(text)
        ):
            self._pending_confirm = text
            self.confirm_needed.emit(text)
            _log(f"Confirm needed ({confidence:.2f}): {text!r}")
            return False
        if self._dup(text):
            _log(f"Skip duplicate: {text!r}")
            return False

        self._last_cmd = text
        self._last_cmd_at = time.time()
        self._last_voice = time.time()
        self._conversation_until = time.time() + CONVERSATION_SEC
        self._mute_until = max(self._mute_until, time.time() + 0.4)
        self._utterance_due = 0.0
        self._commit_cooldown_until = time.time() + COMMIT_COOLDOWN_OK_SEC
        self._turn_frames.clear()
        self._in_turn = False
        self._reset_turn_eou()
        if self._stream_cmd:
            self._stream_cmd.reset()
        if self._stream_grammar:
            self._stream_grammar.reset()
        self._speech_frames.clear()
        self._last_preview = ""

        # App sets assistant_busy when it accepts the command — setting it here
        # caused _handle_assistant_input to drop the utterance and stay stuck.
        self.confidence.emit(confidence)
        self.heard.emit(text)
        self.transcript.emit(text)
        _log(f"RUN ({source} {confidence:.2f}): {text!r}")
        return True

    def _handle_text(self, result: SpeechResult) -> bool:
        text = voice_transcript(result.text)
        if not text:
            return False

        if self._pending_confirm:
            from ui.accessibility_voice import parse_yes_no
            yn = parse_yes_no(text)
            if yn is True:
                pending = self._pending_confirm
                self._pending_confirm = ""
                return self._run_command(pending, confidence=0.92, source="confirmed")
            if yn is False:
                self._pending_confirm = ""
                self.status.emit("Listening…")
                _log("Confirm cancelled")
                return True

        if _has_wake(text):
            extra = _strip_wake(text)
            if self._mode == "conversation":
                if is_wake_only(text) or not extra:
                    _log(f"Skip (wake echo): {text!r}")
                    return True
                text = extra
            elif is_wake_only(text) or not extra:
                if time.time() >= self._greet_lock:
                    self._trigger_wake(text)
                return True
            else:
                text = extra
        return self._run_command(text, confidence=result.confidence, source=result.source)

    def _batch_recognize(self, raw: bytes, *, hint: str = "") -> SpeechResult:
        rate = self._mic.rate
        try:
            return _STT_POOL.submit(
                recognize_batch_command, raw, rate, log_fn=_log, hint=hint,
            ).result(timeout=8.0)
        except Exception as exc:
            _log(f"Batch STT error: {exc}")
            return SpeechResult("", 0.0, "error")

    def _try_execute_phrase(self, phrase: str, *, confidence: float, source: str) -> bool:
        return self._try_execute_utterance(phrase, confidence=confidence, source=source)

    def _flush_speech(self, *, wake: bool) -> None:
        if wake:
            if len(self._speech_frames) < MIN_SPEECH_BLOCKS:
                self._speech_frames.clear()
                self._silent = 0
                return
            raw = LiveMic.join(self._speech_frames)
            self._speech_frames.clear()
            self._silent = 0
            self._try_wake(raw)
            return
        self._commit_turn()

    def _emit_level(self, energy: float, th: float) -> None:
        now = time.time()
        if now - self._last_level_emit >= _MIC_LEVEL_INTERVAL:
            self._last_level_emit = now
            self.mic_level.emit(min(1.0, energy / max(th * 2.0, 1.0)))
        if now - self._last_health_emit >= 2.5:
            self._last_health_emit = now
            self.mic_health.emit(energy, th)

    def _emit_preview(self) -> None:
        if not self._stream_cmd:
            return
        now = time.time()
        preview = self._preview_text()
        if not preview or is_voice_garbage(preview):
            return
        if preview == self._last_preview and now - self._last_preview_emit < _PREVIEW_INTERVAL:
            return
        self._last_preview = preview
        self._last_preview_emit = now
        self.partial_text.emit(preview)

    def run(self) -> None:
        try:
            ensure_vosk_model(_log)
            self._mic = LiveMic()
            self._stream_wake = StreamingWakeListener(self._mic.rate, _has_wake, log_fn=_log)
            self._stream_cmd = StreamingRecognizer(self._mic.rate, log_fn=_log)
            self._stream_grammar = GrammarHintRecognizer(self._mic.rate, log_fn=_log)
        except Exception as exc:
            self.error.emit(f"Mic error: {exc}")
            _log(f"Init fail: {exc}")
            self.mic_ready.emit(False)
            return

        self._running = True
        self.mic_ready.emit(True)
        self._open_idle()
        _log("Voice ready v5.0")

        try:
            while self._running:
                with self._lock:
                    if self._manual:
                        self._manual = False
                        self._ready_at = time.time()
                        self._open_conversation()

                item = self._mic.read()
                if item is None:
                    self._idle_ticks += 1
                    if self._idle_ticks > 2000 and self._mic and self._mic._errors > 5:
                        self._mic.restart()
                        self._idle_ticks = 0
                    continue
                self._idle_ticks = 0

                energy, block = item
                self._mic.note(energy)
                th = self._mic.threshold(sensitive=(self._mode == "idle"))
                self._emit_level(energy, th)

                if self._mode == "idle":
                    if self._stream_wake:
                        hit = self._stream_wake.feed(block)
                        if hit and _has_wake(hit):
                            self._trigger_wake(hit)
                            continue
                    if self._mic.is_speech(energy, sensitive=True):
                        self._speech_frames.append(block)
                        self._silent = 0
                    elif self._speech_frames:
                        self._silent += 1
                        self._speech_frames.append(block)
                        if self._silent >= 5:
                            self._flush_speech(wake=True)
                    continue

                if self._mode != "conversation":
                    continue

                turn_speech = self._is_turn_speech(energy)
                in_wake_grace = time.time() < self._wake_grace_until
                stream_active = turn_speech or energy > self._mic._floor * 1.12

                stream_final = None
                grammar_final = None
                if self._stream_cmd and not in_wake_grace:
                    stream_final = self._stream_cmd.feed(block, speech_active=stream_active)
                if self._stream_grammar:
                    grammar_final = self._stream_grammar.feed(block)
                self._emit_preview()

                if self._stt_busy or self._assistant_busy:
                    continue
                if time.time() < self._commit_cooldown_until:
                    continue

                if turn_speech:
                    self._note_turn_speech(energy)

                if time.time() >= self._conversation_until:
                    if time.time() - self._last_voice > CMD_IDLE_SEC:
                        self._open_idle()
                        continue

                if self._await_greeting and self._greeting_deadline and time.time() >= self._greeting_deadline:
                    self._await_greeting = False
                    self._greeting_deadline = 0.0
                    self._ready_at = time.time() + 0.03
                    _log("Greeting timeout — listening")

                self._speech_frames.append(block)
                if len(self._speech_frames) > MAX_TURN_BLOCKS * 2:
                    self._speech_frames = self._speech_frames[-MAX_TURN_BLOCKS:]

                if turn_speech:
                    self._begin_turn()
                    self._turn_frames.append(block)
                    self._silent = 0
                    if not self._speech_ui:
                        self._speech_ui = True
                        self.speech_started.emit()
                elif self._in_turn:
                    self._turn_frames.append(block)
                    self._silent += 1

                if grammar_final:
                    grammar_final = self._resolve_scroll_hint(grammar_final, self._live_transcript())
                if grammar_final and not self._grammar_is_spurious(grammar_final):
                    self._ensure_turn()
                    self._note_turn_speech(energy)
                    self._schedule_commit(COMMIT_DELAY_GRAMMAR, "grammar")
                    _log(f"Command heard: {grammar_final!r}")
                elif grammar_final:
                    _log(f"Ignored grammar in question: {grammar_final!r}")
                elif stream_final and not _is_noise_fragment(stream_final):
                    self._ensure_turn()
                    self._note_turn_speech(energy)
                    self._schedule_commit(COMMIT_DELAY_SEC, "stream")
                    _log(f"Heard fragment: {stream_final!r}")
                elif stream_final:
                    _log(f"Ignored noise fragment: {stream_final!r}")

                self._tick_end_of_utterance(energy, turn_speech=turn_speech)

                if self._commit_at and time.time() >= self._commit_at:
                    self._commit_turn()
                elif (
                    self._in_turn
                    and self._speech_seen_in_turn
                    and not turn_speech
                    and self._silent >= SILENCE_BLOCKS
                    and self._has_meaningful_utterance()
                    and time.time() >= self._wake_grace_until
                ):
                    self._commit_turn()

        except Exception as exc:
            self.error.emit(str(exc))
            _log(f"Crash: {exc}\n{traceback.format_exc()}")
            self.mic_ready.emit(False)
        finally:
            if self._mic:
                self._mic.stop()
            self.status.emit("Voice off")


class VoiceEngine(QObject):
    wake_detected = pyqtSignal(bool)
    command_listen = pyqtSignal()
    speech_started = pyqtSignal()
    speech_ready = pyqtSignal(str)
    status_changed = pyqtSignal(str)
    mic_available = pyqtSignal(bool)
    error_message = pyqtSignal(str)
    heard_text = pyqtSignal(str)
    mic_level = pyqtSignal(float)
    partial_text = pyqtSignal(str)
    mic_health = pyqtSignal(float, float)
    confidence = pyqtSignal(float)
    confirm_needed = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self._worker: _VoiceWorker | None = None

    def start(self) -> bool:
        if self._worker and self._worker.isRunning():
            return True
        self._worker = _VoiceWorker()
        w = self._worker
        w.wake.connect(self.wake_detected.emit)
        w.command_listen.connect(self.command_listen.emit)
        w.speech_started.connect(self.speech_started.emit)
        w.transcript.connect(self.speech_ready.emit)
        w.status.connect(self.status_changed.emit)
        w.error.connect(self.error_message.emit)
        w.mic_ready.connect(self.mic_available.emit)
        w.heard.connect(self.heard_text.emit)
        w.mic_level.connect(self.mic_level.emit)
        w.partial_text.connect(self.partial_text.emit)
        w.mic_health.connect(self.mic_health.emit)
        w.confidence.connect(self.confidence.emit)
        w.confirm_needed.connect(self.confirm_needed.emit)
        w.start()
        return True

    def set_confirm_enabled(self, enabled: bool) -> None:
        if self._worker and self._worker.isRunning():
            self._worker.set_confirm_enabled(enabled)

    def stop(self) -> None:
        if self._worker:
            self._worker.stop()
            self._worker = None

    def listen_for_command(self) -> None:
        if self._worker and self._worker.isRunning():
            self._worker.listen_command_now()

    def on_greeting_finished(self) -> None:
        if self._worker and self._worker.isRunning():
            self._worker.greeting_finished()

    def notify_tts_start(self, *, greeting: bool = False) -> None:
        if self._worker and self._worker.isRunning():
            self._worker.notify_tts_start(greeting=greeting)

    def notify_tts_finished(self) -> None:
        if self._worker and self._worker.isRunning():
            self._worker.notify_tts_finished()

    def resume_listening(self) -> None:
        if self._worker and self._worker.isRunning():
            self._worker.resume_listening()

    def set_assistant_busy(self, busy: bool) -> None:
        if self._worker and self._worker.isRunning():
            self._worker.set_assistant_busy(busy)

    def is_assistant_busy(self) -> bool:
        if self._worker and self._worker.isRunning():
            return self._worker.is_assistant_busy()
        return False

    def extend_conversation(self) -> None:
        if self._worker and self._worker.isRunning():
            self._worker.extend_conversation()

    @staticmethod
    def is_supported() -> bool:
        try:
            import numpy  # noqa: F401
            import sounddevice  # noqa: F401
            return True
        except ImportError:
            return False
