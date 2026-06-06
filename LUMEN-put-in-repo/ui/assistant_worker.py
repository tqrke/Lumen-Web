"""Background worker — keeps UI responsive during slow assistant calls."""

from __future__ import annotations

from PyQt6.QtCore import QThread, pyqtSignal

from core.perf import perf_span
from ui.assistant import AssistantAction, LumenAssistant, PageContext


class AssistantWorker(QThread):
    """Runs knowledge / Ollama / fallback search off the main thread."""

    finished_ok = pyqtSignal(str, str, object)  # input_text, reply, AssistantAction|None
    failed = pyqtSignal(str, str)  # input_text, error

    def __init__(
        self,
        assistant: LumenAssistant,
        text: str,
        ctx: PageContext,
        *,
        user_name: str,
        prefer_chat: bool = False,
    ):
        super().__init__()
        self._assistant = assistant
        self._text = text
        self._ctx = ctx
        self._user_name = user_name
        self._prefer_chat = prefer_chat

    def run(self) -> None:
        try:
            with perf_span("assistant.process", slow_ms=80.0):
                reply, action = self._assistant.process(
                    self._text,
                    self._ctx,
                    user_name=self._user_name,
                    prefer_chat=self._prefer_chat,
                )
            self.finished_ok.emit(self._text, reply, action)
        except Exception as exc:
            self.failed.emit(self._text, str(exc))
