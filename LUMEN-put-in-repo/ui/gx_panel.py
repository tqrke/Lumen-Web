"""Settings sidebar — luxury card layout."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from ui.theme_manager import list_themes


class _Card(QFrame):
    def __init__(self, colors: dict, title: str, subtitle: str = ""):
        super().__init__()
        c = colors
        jazz = c.get("jazz", c["primary"])
        self.setStyleSheet(f"""
            QFrame {{
                background: {c['bg2']};
                border: 1px solid {c['border']};
                border-radius: 10px;
            }}
        """)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 14)
        lay.setSpacing(8)
        row = QHBoxLayout()
        t = QLabel(title)
        t.setStyleSheet(f"font-size:13px;font-weight:600;color:{c['text']};")
        row.addWidget(t)
        row.addStretch()
        dot = QLabel("●")
        dot.setStyleSheet(f"color:{jazz};font-size:8px;")
        row.addWidget(dot)
        lay.addLayout(row)
        if subtitle:
            s = QLabel(subtitle)
            s.setWordWrap(True)
            s.setStyleSheet(f"font-size:11px;color:{c['text_muted']};margin-bottom:4px;")
            lay.addWidget(s)
        self.body = QVBoxLayout()
        self.body.setSpacing(10)
        lay.addLayout(self.body)


class SettingsPanel(QFrame):
    settings_changed = pyqtSignal(dict)
    clear_cookies_now = pyqtSignal()

    def __init__(self, colors: dict, settings: dict, stats: dict):
        super().__init__()
        self.colors = colors
        self.setFixedWidth(320)
        self._build_ui(colors, settings, stats)

    def _build_ui(self, c: dict, settings: dict, stats: dict) -> None:
        jazz = c.get("jazz", c["primary"])
        self.setStyleSheet(f"""
            QFrame#settingsPanel {{
                background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
                    stop:0 {c['bg1']}, stop:1 {c['bg0']});
                border-left: 1px solid {c['border']};
            }}
            QComboBox {{
                background: {c['bg0']}; color: {c['text']}; font-size: 12px;
                border: 1px solid {c['border']}; border-radius: 6px;
                padding: 8px 12px; min-height: 22px;
            }}
            QComboBox:hover {{ border-color: {c['primary']}; }}
            QComboBox::drop-down {{ border: none; width: 24px; }}
            QCheckBox {{
                color: {c['text']}; font-size: 12px; spacing: 10px;
            }}
            QCheckBox::indicator {{
                width: 18px; height: 18px; border-radius: 4px;
                border: 1px solid {c['border']}; background: {c['bg0']};
            }}
            QCheckBox::indicator:checked {{
                background: {c['primary']}; border-color: {c['primary']};
            }}
            QSlider::groove:horizontal {{
                height: 5px; background: {c['bg0']}; border-radius: 3px;
            }}
            QSlider::handle:horizontal {{
                width: 16px; height: 16px; margin: -6px 0;
                background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
                    stop:0 {c['primary']}, stop:1 {jazz});
                border-radius: 8px;
            }}
            QPushButton.primary {{
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 {c['primary']}, stop:1 {jazz});
                color: #fff; border: none; border-radius: 8px;
                padding: 12px; font-weight: 600; font-size: 12px;
            }}
            QPushButton.primary:hover {{ opacity: 0.9; }}
            QPushButton.ghost {{
                background: transparent; color: {c['text_muted']};
                border: 1px solid {c['border']}; border-radius: 8px;
                padding: 8px; font-size: 11px;
            }}
            QPushButton.ghost:hover {{ border-color: {jazz}; color: {c['text']}; }}
            QPushButton.close {{
                background: transparent; color: {c['text_muted']};
                border: none; font-size: 18px; border-radius: 6px;
            }}
            QPushButton.close:hover {{ background: {c['bg3']}; color: {c['text']}; }}
        """)
        self.setObjectName("settingsPanel")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        head = QHBoxLayout()
        head.setContentsMargins(16, 14, 8, 8)
        title = QLabel("Control Center")
        title.setStyleSheet(f"font-size:16px;font-weight:700;color:{c['text']};")
        close = QPushButton("×")
        close.setProperty("class", "close")
        close.setFixedSize(34, 34)
        close.clicked.connect(self.hide)
        head.addWidget(title)
        head.addStretch()
        head.addWidget(close)
        outer.addLayout(head)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background: transparent; border: none;")

        inner = QWidget()
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(12, 0, 12, 16)
        layout.setSpacing(12)

        # Stats card
        stats_card = _Card(c, "Session", "Live protection metrics")
        self.stats_label = QLabel(self._stats(stats))
        self.stats_label.setStyleSheet(
            f"color:{c['text']};font-size:12px;line-height:1.7;"
            f"padding:8px;background:{c['bg0']};border-radius:6px;"
        )
        self.stats_label.setWordWrap(True)
        stats_card.body.addWidget(self.stats_label)
        layout.addWidget(stats_card)

        # Appearance
        app_card = _Card(c, "Appearance", "Theme and visual style")
        self.theme_combo = QComboBox()
        for t in list_themes():
            self.theme_combo.addItem(t.replace("-", " ").title(), t)
        idx = self.theme_combo.findData(settings.get("theme", "edge-jazz"))
        if idx >= 0:
            self.theme_combo.setCurrentIndex(idx)
        app_card.body.addWidget(self.theme_combo)
        se_lbl = QLabel("Search engine")
        se_lbl.setStyleSheet(f"color:{c['text_muted']};font-size:11px;")
        app_card.body.addWidget(se_lbl)
        self.search_engine = QComboBox()
        for key, (label, _) in [
            ("duckduckgo", ("DuckDuckGo", "")),
            ("brave", ("Brave Search", "")),
            ("searx", ("SearXNG", "")),
            ("wikipedia", ("Wikipedia", "")),
        ]:
            self.search_engine.addItem(label, key)
        idx_se = self.search_engine.findData(settings.get("search_engine", "duckduckgo"))
        if idx_se >= 0:
            self.search_engine.setCurrentIndex(idx_se)
        app_card.body.addWidget(self.search_engine)
        layout.addWidget(app_card)

        # Privacy & shields
        priv_card = _Card(c, "Privacy & Shields", "Block threats and trackers")
        self.ad_block = QCheckBox("Block ads and trackers")
        self.ad_block.setChecked(settings.get("ad_block", True))
        priv_card.body.addWidget(self.ad_block)
        self.firewall = QCheckBox("Block unsafe websites")
        self.firewall.setChecked(settings.get("firewall", True))
        priv_card.body.addWidget(self.firewall)
        lbl = QLabel("Block level")
        lbl.setStyleSheet(f"color:{c['text_muted']};font-size:11px;")
        priv_card.body.addWidget(lbl)
        self.block_level = QComboBox()
        self.block_level.addItems(["standard", "aggressive", "paranoid"])
        self.block_level.setCurrentText(settings.get("block_level", "aggressive"))
        priv_card.body.addWidget(self.block_level)
        layout.addWidget(priv_card)

        # Security sweep
        sec_card = _Card(c, "Security Sweep", "Privacy and automation")
        self.auto_cookies = QCheckBox("Auto-clear cookies (off by default — keeps you signed in)")
        self.auto_cookies.setChecked(settings.get("auto_clear_cookies", False))
        sec_card.body.addWidget(self.auto_cookies)
        self.auto_accept = QCheckBox("Auto-accept cookie banners on sites")
        self.auto_accept.setChecked(settings.get("auto_accept_cookies", True))
        sec_card.body.addWidget(self.auto_accept)
        name_lbl = QLabel("Your name (voice greeting)")
        name_lbl.setStyleSheet(f"color:{c['text_muted']};font-size:11px;")
        sec_card.body.addWidget(name_lbl)
        self.user_name = QLineEdit()
        self.user_name.setText(settings.get("user_name", "Josh"))
        self.user_name.setPlaceholderText("Josh")
        self.user_name.setStyleSheet(
            f"background:{c['bg0']};color:{c['text']};border:1px solid {c['border']};"
            f"border-radius:6px;padding:8px;"
        )
        sec_card.body.addWidget(self.user_name)
        self.secure_mode = QCheckBox("Strict fingerprint protection")
        self.secure_mode.setChecked(settings.get("secure_mode", True))
        sec_card.body.addWidget(self.secure_mode)
        self.voice_control = QCheckBox('Voice control — say "Lumen"')
        self.voice_control.setChecked(settings.get("voice_control", True))
        sec_card.body.addWidget(self.voice_control)
        clear_now = QPushButton("Clear cookies now")
        clear_now.setProperty("class", "ghost")
        clear_now.setCursor(Qt.CursorShape.PointingHandCursor)
        clear_now.clicked.connect(self.clear_cookies_now.emit)
        sec_card.body.addWidget(clear_now)
        layout.addWidget(sec_card)

        ai_card = _Card(c, "LUMEN Mind AI", "Free unlimited knowledge — no subscription")
        ai_note = QLabel(
            "Answers use Wikipedia and the open web automatically. "
            "No API keys, no fees. Install Ollama locally for even smarter replies (optional)."
        )
        ai_note.setWordWrap(True)
        ai_note.setStyleSheet(f"color:{c['text_muted']};font-size:10px;")
        ai_card.body.addWidget(ai_note)
        self.spoken_replies = QCheckBox("Speak replies after voice commands")
        self.spoken_replies.setChecked(settings.get("spoken_replies", True))
        ai_card.body.addWidget(self.spoken_replies)
        self.ai_provider = QComboBox()
        self.ai_provider.addItem("Free knowledge", "builtin")
        self.ai_provider.setCurrentIndex(0)
        self.ai_provider.hide()
        self.openai_api_key = QLineEdit()
        self.openai_api_key.hide()
        self.openai_model = QLineEdit()
        self.openai_model.setText(settings.get("openai_model", "gpt-4o-mini"))
        self.openai_model.hide()
        self.use_ollama = QCheckBox("Ollama fallback")
        self.use_ollama.setChecked(settings.get("use_ollama", False))
        self.use_ollama.hide()
        layout.addWidget(ai_card)

        a11y_card = _Card(
            c,
            "Accessibility & Voice",
            "Designed for hands-free and assistive use",
        )
        self.continuous_voice = QCheckBox("Continuous conversation (2 min after wake)")
        self.continuous_voice.setChecked(settings.get("continuous_voice", True))
        a11y_card.body.addWidget(self.continuous_voice)
        self.confirm_low = QCheckBox("Confirm when command confidence is low")
        self.confirm_low.setChecked(settings.get("confirm_low_confidence", True))
        a11y_card.body.addWidget(self.confirm_low)
        self.a11y_announce = QCheckBox("Spoken status announcements")
        self.a11y_announce.setChecked(settings.get("accessibility_announcements", True))
        a11y_card.body.addWidget(self.a11y_announce)
        wake_lbl = QLabel('Wake word (say this to activate)')
        wake_lbl.setStyleSheet(f"color:{c['text_muted']};font-size:11px;")
        a11y_card.body.addWidget(wake_lbl)
        self.wake_word = QLineEdit()
        self.wake_word.setText(settings.get("wake_word", "lumen"))
        self.wake_word.setPlaceholderText("lumen")
        self.wake_word.setStyleSheet(
            f"background:{c['bg0']};color:{c['text']};border:1px solid {c['border']};"
            f"border-radius:6px;padding:8px;"
        )
        a11y_card.body.addWidget(self.wake_word)
        layout.addWidget(a11y_card)

        # Performance
        perf_card = _Card(c, "Performance", "Memory and tab management")
        self.ram_saver = QCheckBox("Suspend inactive tabs")
        self.ram_saver.setChecked(settings.get("ram_saver", True))
        perf_card.body.addWidget(self.ram_saver)
        hl = QLabel("Hibernate after (minutes)")
        hl.setStyleSheet(f"color:{c['text_muted']};font-size:11px;")
        perf_card.body.addWidget(hl)
        self.hibernate_slider = QSlider(Qt.Orientation.Horizontal)
        self.hibernate_slider.setRange(1, 30)
        self.hibernate_slider.setValue(settings.get("hibernate_mins", 5))
        self.hibernate_val = QLabel(str(self.hibernate_slider.value()))
        self.hibernate_val.setStyleSheet(f"color:{jazz};font-size:11px;font-weight:600;")
        self.hibernate_slider.valueChanged.connect(
            lambda v: self.hibernate_val.setText(str(v))
        )
        perf_card.body.addWidget(self.hibernate_slider)
        perf_card.body.addWidget(self.hibernate_val)
        layout.addWidget(perf_card)

        apply_btn = QPushButton("Save changes")
        apply_btn.setProperty("class", "primary")
        apply_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        apply_btn.clicked.connect(self._emit)
        layout.addWidget(apply_btn)
        layout.addStretch()

        scroll.setWidget(inner)
        outer.addWidget(scroll, 1)

    def _stats(self, stats: dict) -> str:
        return (
            f"🛡  Ads blocked: {stats.get('ads', 0):,}\n"
            f"⛔  Threats stopped: {stats.get('threats', 0):,}\n"
            f"🔒  VPN tunnel: {stats.get('vpn_kb', 0):,} KB"
        )

    def update_stats(self, stats: dict) -> None:
        self.stats_label.setText(self._stats(stats))

    def _emit(self) -> None:
        self.settings_changed.emit({
            "theme": self.theme_combo.currentData(),
            "search_engine": self.search_engine.currentData(),
            "ad_block": self.ad_block.isChecked(),
            "block_level": self.block_level.currentText(),
            "firewall": self.firewall.isChecked(),
            "ram_saver": self.ram_saver.isChecked(),
            "hibernate_mins": self.hibernate_slider.value(),
            "auto_clear_cookies": self.auto_cookies.isChecked(),
            "auto_accept_cookies": self.auto_accept.isChecked(),
            "user_name": self.user_name.text().strip() or "Josh",
            "secure_mode": self.secure_mode.isChecked(),
            "voice_control": self.voice_control.isChecked(),
            "ai_provider": "builtin",
            "openai_model": self.openai_model.text().strip() or "gpt-4o-mini",
            "use_ollama": self.use_ollama.isChecked(),
            "spoken_replies": self.spoken_replies.isChecked(),
            "continuous_voice": self.continuous_voice.isChecked(),
            "confirm_low_confidence": self.confirm_low.isChecked(),
            "accessibility_announcements": self.a11y_announce.isChecked(),
            "wake_word": self.wake_word.text().strip().lower() or "lumen",
        })


GXPanel = SettingsPanel
