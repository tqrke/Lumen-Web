"""LUMEN Mind — AI sidebar with voice control."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ui.assistant import LumenAssistant, PageContext
from ui.icons import IconButton


class AIPanel(QFrame):
    action_requested = pyqtSignal(str, str)
    summarize_requested = pyqtSignal()
    voice_command_requested = pyqtSignal()
    query_submitted = pyqtSignal(str)

    def __init__(self, colors: dict):
        super().__init__()
        self.colors = colors
        self.assistant = LumenAssistant()
        self._context = PageContext()
        self._user_name = "Josh"
        self._voice_active = False
        self.setFixedWidth(360)
        self._build(colors)

    def _build(self, c: dict) -> None:
        jazz = c.get("jazz", c["primary"])
        self.setStyleSheet(f"""
            QFrame#aiPanel {{
                background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
                    stop:0 {c['bg1']}, stop:1 {c['bg0']});
                border-left: 1px solid {c['border']};
            }}
            QTextEdit {{
                background: {c['bg0']}; color: {c['text']};
                border: 1px solid {c['border']}; border-radius: 8px;
                padding: 12px; font-size: 13px; line-height: 1.5;
            }}
            QLineEdit {{
                background: {c['bg2']}; color: {c['text']};
                border: 1px solid {c['border']}; border-radius: 8px;
                padding: 12px 14px; font-size: 13px;
            }}
            QLineEdit:focus {{ border-color: {c['primary']}; }}
            QLineEdit.listening {{
                border-color: {jazz};
            }}
            QPushButton.send {{
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 {c['primary']}, stop:1 {jazz});
                color: #fff; border: none; border-radius: 8px;
                padding: 12px 16px; font-weight: 600; font-size: 12px;
            }}
            QPushButton.chip {{
                background: {c['bg2']}; color: {c['text']};
                border: 1px solid {c['border']}; border-radius: 14px;
                padding: 6px 12px; font-size: 11px;
            }}
            QPushButton.chip:hover {{ border-color: {jazz}; color: {jazz}; }}
            QPushButton.close {{
                background: transparent; color: {c['text_muted']};
                border: none; font-size: 18px; border-radius: 6px;
            }}
            QPushButton.close:hover {{ background: {c['bg3']}; color: {c['text']}; }}
        """)
        self.setObjectName("aiPanel")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        head_card = QFrame()
        head_card.setStyleSheet(f"""
            QFrame {{
                background: {c['bg2']}; border-bottom: 1px solid {c['border']};
                border-left: 3px solid {jazz};
            }}
        """)
        head = QHBoxLayout(head_card)
        head.setContentsMargins(16, 14, 8, 14)
        titles = QVBoxLayout()
        t = QLabel("LUMEN Mind")
        t.setStyleSheet(f"font-size:15px;font-weight:700;color:{c['text']};letter-spacing:0.3px;")
        self.status = QLabel('Always listening · say "Lumen"')
        self.status.setStyleSheet(f"font-size:11px;color:{c['text_muted']};")
        titles.addWidget(t)
        titles.addWidget(self.status)
        head.addLayout(titles)
        head.addStretch()
        close = QPushButton("×")
        close.setProperty("class", "close")
        close.setFixedSize(34, 34)
        close.setCursor(Qt.CursorShape.PointingHandCursor)
        close.clicked.connect(self.hide)
        head.addWidget(close)
        layout.addWidget(head_card)

        chips_wrap = QWidget()
        chips = QHBoxLayout(chips_wrap)
        chips.setContentsMargins(12, 10, 12, 4)
        chips.setSpacing(6)
        for label, cmd in [
            ("Map", "map of London"),
            ("Weather", "weather in Paris"),
            ("Tesco", "open tesco"),
            ("Search Tesco", "search spaghetti"),
            ("Video", "play lofi hip hop on youtube"),
            ("Summarize", "summarize this page"),
            ("News", "latest tech news"),
            ("Wiki", "what is AI"),
            ("Test mic", "__voice_test__"),
        ]:
            b = QPushButton(label)
            b.setProperty("class", "chip")
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            if cmd == "__voice_test__":
                b.clicked.connect(self.voice_command_requested.emit)
            else:
                b.clicked.connect(lambda _, cmd=cmd: self._send(cmd))
            chips.addWidget(b)
        layout.addWidget(chips_wrap)

        self.chat = QTextEdit()
        self.chat.setReadOnly(True)
        self.chat.setPlaceholderText("Maps, weather, videos, directions — ask for anything.")
        layout.addWidget(self.chat, 1)

        inp_wrap = QFrame()
        inp_wrap.setStyleSheet(f"background:{c['bg1']}; border-top:1px solid {c['border']};")
        inp_row = QHBoxLayout(inp_wrap)
        inp_row.setContentsMargins(12, 12, 12, 14)
        inp_row.setSpacing(6)
        self.mic_btn = IconButton("mic", "Voice command", c, 36)
        self.mic_btn.clicked.connect(self._on_mic)
        self.input = QLineEdit()
        self.input.setPlaceholderText("Type or speak your request…")
        self.input.returnPressed.connect(self._on_send)
        send = QPushButton("Run")
        send.setProperty("class", "send")
        send.setCursor(Qt.CursorShape.PointingHandCursor)
        send.clicked.connect(self._on_send)
        inp_row.addWidget(self.mic_btn)
        inp_row.addWidget(self.input, 1)
        inp_row.addWidget(send)
        layout.addWidget(inp_wrap)

        self._append(
            "assistant",
            "I'm LUMEN Mind — free knowledge with unlimited memory. "
            "Say \"Lumen\", ask one question at a time, then wait for my reply. "
            "Try: what is AI, tell me more, remember I like jazz, open YouTube.",
        )

    def set_user_name(self, name: str) -> None:
        self._user_name = (name or "Josh").strip() or "Josh"
        self.assistant.configure(user_name=self._user_name)

    def set_ai_status(self, provider: str, ready: bool, model: str = "") -> None:
        if provider == "Local AI" and model:
            self.status.setText(f'Local AI · {model} · say "Lumen"')
        elif provider == "Free knowledge":
            self.status.setText('Free knowledge · Wikipedia · say "Lumen"')
        else:
            self.status.setText('Say "Lumen" to talk')

    def set_ollama_status(self, ready: bool, model: str = "") -> None:
        self.set_ai_status("Ollama" if ready else "Built-in", ready, model)

    def record_exchange(self, user: str, reply: str, *, user_already_shown: bool = False) -> None:
        if not user_already_shown:
            self._append("user", user)
        self._append("assistant", reply)
        self.set_context_hint(self._context)

    def _on_mic(self) -> None:
        self.set_listening(True)
        self.voice_command_requested.emit()

    def set_listening(self, on: bool) -> None:
        self._voice_active = on
        jazz = self.colors.get("jazz", self.colors["primary"])
        if on:
            self.input.setPlaceholderText("Listening… speak now")
            self.input.setStyleSheet(
                f"background:{self.colors['bg2']}; color:{self.colors['text']}; "
                f"border:1px solid {jazz}; border-radius:8px; padding:12px 14px;"
            )
        else:
            self.input.setPlaceholderText("Type or speak your request…")
            self.input.setStyleSheet("")

    def set_voice_status(self, text: str) -> None:
        self.status.setText(text)

    def apply_voice_transcript(self, text: str, auto_run: bool = True) -> None:
        text = text.strip()
        if not text:
            self.set_listening(False)
            self.set_voice_status('Always listening · say "Lumen"')
            return
        self.input.setText(text)
        self.set_listening(False)
        if auto_run:
            self._send(text)

    def set_context_hint(self, ctx: PageContext) -> None:
        self._context = ctx
        if self._voice_active:
            return
        if ctx.url and not ctx.url.startswith("lumen://"):
            title = (ctx.title[:36] + "…") if len(ctx.title) > 36 else (ctx.title or "page")
            extra = " · ChatGPT" if self.assistant.chat_ready() else ""
            self.status.setText(f"Viewing {title}{extra}")
        else:
            self.status.setText('Always listening · say "Lumen"')

    def show_summary(self, text: str) -> None:
        self._append("assistant", text)

    def _on_send(self) -> None:
        self._send(self.input.text())

    def _send(self, message: str) -> None:
        message = message.strip()
        if not message:
            return
        self.input.clear()
        self.set_listening(False)
        self._append("user", message)
        self.status.setText("Thinking…")
        self.query_submitted.emit(message)

    def set_page_context(self, ctx: PageContext) -> None:
        self._context = ctx

    def _append(self, role: str, text: str) -> None:
        c = self.colors
        if role == "user":
            bubble_bg = c["bg3"]
            label = "You"
            color = c["text"]
        else:
            bubble_bg = c["bg2"]
            label = "Mind"
            color = c["text"]
        jazz = c.get("jazz", c["primary"])
        accent = jazz if role == "assistant" else c["text_muted"]
        safe = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        safe = safe.replace("**", "")
        self.chat.append(
            f'<div style="margin:10px 4px;">'
            f'<p style="margin:0 0 4px;font-size:10px;color:{accent};font-weight:600;">{label}</p>'
            f'<p style="margin:0;padding:10px 12px;background:{bubble_bg};'
            f'border-radius:8px;color:{color};line-height:1.55;border-left:2px solid '
            f'{jazz if role == "assistant" else c["primary"]};">{safe}</p></div>'
        )
        sb = self.chat.verticalScrollBar()
        sb.setValue(sb.maximum())
