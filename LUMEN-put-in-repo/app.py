"""LUMEN Browser — clean, minimal, Edge-inspired."""

from __future__ import annotations

import json
import os
import random
import re
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from PyQt6.QtCore import QTimer, QUrl, Qt, pyqtSignal, QEvent
from PyQt6.QtGui import QAction, QIcon, QKeySequence
from PyQt6.QtWebEngineCore import (
    QWebEnginePage,
    QWebEngineProfile,
    QWebEngineSettings,
)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QTabBar,
    QVBoxLayout,
    QWidget,
)

from core.accounts import AccountManager
from core.browser_identity import apply_browser_identity
from core.paths import ASSETS, BOOKMARKS_PATH, SETTINGS_PATH, STORAGE_PATH, WEB_CACHE_PATH
from core.edge_session import edge_eval_grocery, edge_eval_page, edge_is_active, edge_search_tesco, open_grocery_in_edge
from core.retail_loader import is_retail_grocery_url, on_retail_load_finished, open_system_browser
from ui.edge_tab import EDGE_TAB_AVAILABLE, EdgeTab
from core.perf import mark, perf_span, session_summary, start_tracing
from shields.engine import get_shields
from shields.interceptor import LumenRequestInterceptor
from ui.ai_panel import AIPanel
from ui.assistant import AssistantAction, PageContext
from ui.assistant_worker import AssistantWorker
from ui.block_page import threat_block_html
from ui.cookie_helper import COOKIE_DISMISS_JS
from ui.gx_panel import SettingsPanel
from ui.icons import IconButton
from ui.command_sanitize import looks_like_question, sanitize_command, voice_transcript, wants_spoken_answer
from ui.login_dialog import LoginDialog
from ui.mind_bubble import MindBubble
from ui.media_control import MEDIA_CONTROL_JS
from ui.theme_manager import global_stylesheet, load_theme
from ui.title_bar import TitleBar
from ui.wake_words import is_tts_garbage, is_wake_only, looks_like_command, normalize_command
from ui.accessibility_voice import announce, confirm_question, error_phrase
from ui.conversation_session import get_session
from ui.command_router import match_fast_command
from ui.intent_engine import IntentResult, resolve_intent, should_use_browser_intent
from ui.tts import greet_user, prewarm_greeting, speak_ack, speak_reply
from ui.voice_engine import VoiceEngine
from vpn.tunnel import LumenVPN

FREE_ENGINES = {
    "duckduckgo": ("DuckDuckGo", "https://duckduckgo.com/?q={}"),
    "brave": ("Brave Search", "https://search.brave.com/search?q={}"),
    "searx": ("SearXNG", "https://searx.be/search?q={}"),
    "wikipedia": ("Wikipedia", "https://en.wikipedia.org/wiki/Special:Search?search={}"),
}

DEFAULT_SETTINGS = {
    "search_engine": "duckduckgo",
    "homepage": "lumen://start",
    "theme": "edge-jazz",
    "ad_block": True,
    "firewall": True,
    "block_level": "aggressive",
    "ram_saver": True,
    "hibernate_mins": 5,
    "animations": True,
    "auto_clear_cookies": False,
    "secure_mode": True,
    "voice_control": True,
    "auto_accept_cookies": True,
    "user_name": "Josh",
    "spoken_replies": True,
    "use_ollama": False,
    "ai_provider": "builtin",
    "lumen_ai_url": "",
    "lumen_client_token": "",
    "openai_api_key": "",
    "openai_model": "gpt-4o-mini",
    "continuous_voice": True,
    "confirm_low_confidence": False,
    "accessibility_announcements": True,
    "wake_word": "lumen",
}

APP_VERSION = "5.0.0"

_FAST_VOICE_KINDS = frozenset({
    "navigate", "grocery", "media", "scroll", "back", "forward", "reload", "new_tab", "app", "search",
})


def _log_voice_app(msg: str) -> None:
    try:
        log_path = Path.home() / ".lumen" / "voice.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as f:
            f.write(f"{datetime.now():%H:%M:%S} APP: {msg}\n")
    except OSError:
        pass


def load_json(path: Path, default):
    try:
        if path.exists():
            data = {**default, **json.loads(path.read_text(encoding="utf-8"))}
            return _migrate_settings(data)
    except (json.JSONDecodeError, OSError):
        pass
    return dict(default)


def _migrate_settings(data: dict) -> dict:
    """Free built-in knowledge — no API keys or subscriptions."""
    provider = str(data.get("ai_provider", "builtin")).lower()
    if provider in ("lumen", "openai") and not str(data.get("openai_api_key", "")).strip():
        data["ai_provider"] = "builtin"
    return data


def save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def app_icon() -> QIcon:
    for p in (ASSETS / "lumen.ico", ASSETS / "lumen-icon.png"):
        if p.exists():
            return QIcon(str(p))
    return QIcon()


def perf_chromium_flags(*, secure: bool = True) -> str:
    """Chromium flags — direct network (no SOCKS) so Akamai sees a normal browser."""
    flags = [
        "--disable-blink-features=AutomationControlled",
        "--disable-background-networking",
        "--disable-extensions",
        "--disable-sync",
        "--disable-translate",
        "--disable-default-apps",
        "--renderer-process-limit=6",
        "--disk-cache-size=134217728",
        "--enable-gpu-rasterization",
        "--ignore-gpu-blocklist",
    ]
    if secure:
        flags.append("--enable-features=NetworkService,NetworkServiceInProcess")
    return " ".join(flags)


class LumenWebPage(QWebEnginePage):
    threat_blocked = pyqtSignal(str, str)
    ad_blocked_signal = pyqtSignal(str)

    def __init__(self, profile, browser, parent=None):
        super().__init__(profile, parent)
        self._browser = browser

    def acceptNavigationRequest(self, url, nav_type, is_main_frame):
        u = url.toString()
        if u.startswith("lumen://"):
            if u == "lumen://start" and is_main_frame:
                return True
            if u.startswith("lumen://force?") and is_main_frame:
                from urllib.parse import unquote
                real = unquote(u.split("?", 1)[1])
                self._browser.allow_once.add(real)
                QTimer.singleShot(0, lambda r=real: self.setUrl(QUrl(r)))
                return False
            if u == "lumen://login" and is_main_frame:
                QTimer.singleShot(0, self._browser.show_login_dialog)
                return False
            return False

        if u in self._browser.allow_once:
            self._browser.allow_once.discard(u)
            return super().acceptNavigationRequest(url, nav_type, is_main_frame)

        shields = get_shields()
        shields.ad_block_enabled = self._browser.settings.get("ad_block", True)
        shields.firewall_enabled = self._browser.settings.get("firewall", True)
        shields.block_level = self._browser.settings.get("block_level", "aggressive")

        if not is_main_frame and shields.is_ad_url(u):
            shields.record_ad_block()
            return False

        if is_main_frame:
            is_threat, reason = shields.check_threat(u)
            if is_threat:
                shields.record_threat_block()
                self.threat_blocked.emit(u, reason)
                html = threat_block_html(u, reason, self._browser.colors)
                self.setHtml(html, QUrl("lumen://blocked"))
                return False

        return super().acceptNavigationRequest(url, nav_type, is_main_frame)


class BrowserTab(QWebEngineView):
    def __init__(self, profile, browser, parent=None):
        super().__init__(parent)
        self._browser = browser
        self._hibernating = False
        self._last_active = time.time()
        self._saved_url = ""
        page = LumenWebPage(profile, browser, self)
        self._dev_page = QWebEnginePage(profile)
        page.setDevToolsPage(self._dev_page)
        self.setPage(page)
        s = self.settings()
        s.setAttribute(QWebEngineSettings.WebAttribute.LocalStorageEnabled, True)
        s.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        s.setAttribute(QWebEngineSettings.WebAttribute.ScrollAnimatorEnabled, False)
        s.setAttribute(QWebEngineSettings.WebAttribute.Accelerated2dCanvasEnabled, True)
        s.setAttribute(QWebEngineSettings.WebAttribute.WebGLEnabled, True)
        s.setAttribute(QWebEngineSettings.WebAttribute.PluginsEnabled, False)
        s.setAttribute(QWebEngineSettings.WebAttribute.AutoLoadIconsForPage, False)
        s.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

    def _show_context_menu(self, pos) -> None:
        menu = self.createStandardContextMenu()
        if menu is None:
            menu = QMenu(self)
        menu.addSeparator()
        inspect = menu.addAction("Inspect element")
        inspect.setShortcut("Ctrl+Shift+C")
        inspect.triggered.connect(lambda: self._browser._open_devtools(self, pick=True))
        menu.exec(self.mapToGlobal(pos))


class LumenBrowser(QMainWindow):
    def __init__(self, vpn: LumenVPN, profile: QWebEngineProfile):
        super().__init__()
        self.vpn = vpn
        self.profile = profile
        self.settings = load_json(SETTINGS_PATH, DEFAULT_SETTINGS)
        self.bookmarks = load_json(BOOKMARKS_PATH, [])
        self.accounts = AccountManager()
        self.colors = load_theme(self.settings.get("theme", "edge-jazz"))
        self.allow_once: set[str] = set()
        self._views: list[BrowserTab] = []
        self._start_html_cache = ""
        self._icon_buttons: list[IconButton] = []
        self._devtools_visible = False

        self.setWindowTitle("LUMEN Browser")
        self.setMinimumSize(1100, 720)
        self.resize(1440, 920)
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)
        self.setWindowIcon(app_icon())

        self._build_ui()
        self._build_shortcuts()
        self.apply_theme()
        self.add_tab(self.settings.get("homepage", "lumen://start"))

        self._hibernate_timer = QTimer()
        self._hibernate_timer.timeout.connect(self._hibernate_inactive_tabs)
        self._hibernate_timer.start(60000)

        self._cookie_timer = QTimer()
        self._cookie_timer.timeout.connect(self._privacy_sweep)

    def _icon(self, name: str, tip: str, size: int = 32) -> IconButton:
        btn = IconButton(name, tip, self.colors, size)
        self._icon_buttons.append(btn)
        return btn

    def _style_chrome(self) -> None:
        """Re-apply inline styles after theme change."""
        c = self.colors
        if hasattr(self, "tab_strip"):
            self.tab_strip.setStyleSheet(f"background:{c['bg1']}; border:none;")
        if hasattr(self, "nav"):
            self.nav.setStyleSheet(
                f"background:{c['bg1']}; border-bottom:1px solid {c['border']};"
            )
        if hasattr(self, "omnibox_frame"):
            self.omnibox_frame.setStyleSheet(f"""
                QFrame {{
                    background:{c['omnibox']}; border:1px solid {c['border']};
                    border-radius:4px;
                }}
                QFrame:focus-within {{ border-color:{c['primary']}; }}
            """)
        if hasattr(self, "omnibox"):
            self.omnibox.setStyleSheet(
                f"QLineEdit {{ background:transparent; color:{c['text']}; "
                f"font-size:13px; padding:6px 0; border:none; }}"
            )
        for btn in self._icon_buttons:
            btn.apply_colors(c)
        if hasattr(self, "ai_panel"):
            self.ai_panel.colors = c

    def _build_ui(self) -> None:
        shell = QWidget()
        self.setCentralWidget(shell)
        root = QVBoxLayout(shell)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        main_col = QWidget()
        layout = QVBoxLayout(main_col)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.title_bar = TitleBar(self, "", self.colors)
        layout.addWidget(self.title_bar)

        c = self.colors

        # Tab strip — + sits right after tabs (Edge style)
        self.tab_strip = QFrame()
        self.tab_strip.setFixedHeight(40)
        tsl = QHBoxLayout(self.tab_strip)
        tsl.setContentsMargins(8, 0, 8, 0)
        tsl.setSpacing(0)
        self.tab_bar = QTabBar()
        self.tab_bar.setExpanding(False)
        self.tab_bar.setDrawBase(False)
        self.tab_bar.setMovable(True)
        self.tab_bar.setTabsClosable(True)
        self.tab_bar.tabCloseRequested.connect(self.close_tab)
        self.tab_bar.currentChanged.connect(self._on_tab_changed)
        tsl.addWidget(self.tab_bar)
        self.new_tab_btn = self._icon("plus", "New tab (Ctrl+T)", 28)
        self.new_tab_btn.clicked.connect(lambda: self.add_tab())
        tsl.addWidget(self.new_tab_btn)
        tsl.addStretch(1)
        layout.addWidget(self.tab_strip)

        # Navigation toolbar
        self.nav = QFrame()
        self.nav.setFixedHeight(48)
        nl = QHBoxLayout(self.nav)
        nl.setContentsMargins(6, 4, 8, 4)
        nl.setSpacing(0)
        self.back_btn = self._icon("back", "Back (Alt+Left)")
        self.fwd_btn = self._icon("forward", "Forward (Alt+Right)")
        self.reload_btn = self._icon("reload", "Refresh (Ctrl+R)")
        self.back_btn.clicked.connect(lambda: self.current_view() and self.current_view().back())
        self.fwd_btn.clicked.connect(lambda: self.current_view() and self.current_view().forward())
        self.reload_btn.clicked.connect(self._reload)
        nl.addWidget(self.back_btn)
        nl.addWidget(self.fwd_btn)
        nl.addWidget(self.reload_btn)

        sep = QFrame()
        sep.setFixedWidth(1)
        sep.setStyleSheet(f"background:{c['border']}; margin:8px 6px;")
        nl.addWidget(sep)

        self.omnibox_frame = QFrame()
        obl = QHBoxLayout(self.omnibox_frame)
        obl.setContentsMargins(10, 0, 10, 0)
        obl.setSpacing(8)
        self.secure_icon = QLabel()
        self.secure_icon.setFixedWidth(8)
        self.secure_icon.setFixedHeight(8)
        obl.addWidget(self.secure_icon)
        self.omnibox = QLineEdit()
        self.omnibox.setPlaceholderText("Search or enter a web address")
        self.omnibox.setFrame(False)
        self.omnibox.returnPressed.connect(self._navigate)
        obl.addWidget(self.omnibox, 1)
        nl.addWidget(self.omnibox_frame, 1)

        self.ai_btn = self._icon("ai", "LUMEN Mind assistant (Ctrl+Shift+A)")
        self.ai_btn.clicked.connect(self._toggle_ai)
        self.inspect_btn = self._icon("inspect", "Inspect element (Ctrl+Shift+C)")
        self.inspect_btn.clicked.connect(lambda: self._open_devtools(pick=True))
        self.bookmark_btn = self._icon("bookmark", "Bookmarks")
        self.bookmark_btn.clicked.connect(self._show_bookmarks_menu)
        self._bookmarks_menu = QMenu(self)
        self._bookmarks_menu.aboutToShow.connect(self._populate_bookmarks_menu)
        self.account_btn = self._icon("user", "LUMEN Account (optional)")
        self.account_btn.clicked.connect(self._show_account_menu)
        self._account_menu = QMenu(self)
        self._account_menu.aboutToShow.connect(self._populate_account_menu)
        self.settings_btn = self._icon("settings", "Settings")
        self.settings_btn.clicked.connect(self._toggle_settings)
        nl.addWidget(self.ai_btn)
        nl.addWidget(self.inspect_btn)
        nl.addWidget(self.bookmark_btn)
        nl.addWidget(self.account_btn)
        nl.addWidget(self.settings_btn)
        layout.addWidget(self.nav)

        self._style_chrome()

        self.browser_container = QWidget()
        bc_layout = QVBoxLayout(self.browser_container)
        bc_layout.setContentsMargins(0, 0, 0, 0)
        bc_layout.setSpacing(0)

        self.content_split = QSplitter(Qt.Orientation.Vertical)
        self.content_split.setHandleWidth(1)
        self.content_split.setChildrenCollapsible(False)
        self.content_split.setStyleSheet(f"QSplitter::handle {{ background:{c['border']}; }}")

        self.stack = QStackedWidget()
        self.devtools_view = QWebEngineView()
        self.devtools_view.setMinimumHeight(180)
        self.devtools_view.setVisible(False)
        self.content_split.addWidget(self.stack)
        self.content_split.addWidget(self.devtools_view)
        self.content_split.setSizes([1000, 0])
        self.content_split.setStretchFactor(0, 1)
        self.content_split.setStretchFactor(1, 0)
        bc_layout.addWidget(self.content_split, 1)
        layout.addWidget(self.browser_container, 1)

        # Side panels float on the right — never cover the whole page (no grey overlay)
        self.settings_panel = SettingsPanel(self.colors, self.settings, self._session_stats())
        self.settings_panel.setParent(self.browser_container)
        self.settings_panel.settings_changed.connect(self._apply_settings)
        self.settings_panel.clear_cookies_now.connect(self._privacy_sweep)
        self.settings_panel.hide()

        self.ai_panel = AIPanel(self.colors)
        self.ai_panel.setParent(self.browser_container)
        self.ai_panel.action_requested.connect(self._ai_action)
        self.ai_panel.summarize_requested.connect(self._ai_summarize)
        self.ai_panel.voice_command_requested.connect(self._voice_command)
        self.ai_panel.query_submitted.connect(
            lambda text: self._handle_assistant_input(text, from_voice=False)
        )
        self.ai_panel.hide()

        self.voice = VoiceEngine()
        self.voice.wake_detected.connect(self._on_hey_mind)
        self.voice.command_listen.connect(self._on_command_listen)
        self.voice.speech_started.connect(self._on_speech_started)
        self.voice.speech_ready.connect(self._on_voice_speech)
        self.voice.status_changed.connect(self._on_voice_status)
        self.voice.error_message.connect(self._on_voice_error)
        self.voice.mic_available.connect(self._on_mic_available)
        self.voice.heard_text.connect(self._on_voice_debug)
        self.voice.mic_level.connect(self._on_mic_level)
        self.voice.partial_text.connect(self._on_voice_partial)
        self.voice.mic_health.connect(self._on_mic_health)
        self.voice.confirm_needed.connect(self._on_voice_confirm)
        self._assistant_worker: AssistantWorker | None = None
        self._voice_processing = False
        self._auto_scrolling = False

        # CRITICAL: attach main_col to shell root — NOT to its own layout (causes grey screen)
        root.addWidget(main_col, 1)

        self.mind_bubble = MindBubble(self.browser_container, self.colors)
        self.mind_bubble.clicked.connect(self._on_bubble_listen)
        self._bubble_sync = QTimer(self)
        self._bubble_sync.timeout.connect(self._position_mind_bubble)
        self._bubble_sync.start(400)

        self.ai_panel.set_user_name(self.settings.get("user_name", "Josh"))
        QTimer.singleShot(400, self._init_assistant_brain)
        QTimer.singleShot(1200, self._prompt_account_unlock)

    def _prompt_account_unlock(self) -> None:
        if self.accounts.username and not self.accounts.logged_in:
            self.show_login_dialog(self.accounts.username)

    def show_login_dialog(self, username_hint: str = "") -> None:
        dlg = LoginDialog(self.colors, self.accounts, username_hint=username_hint or "")
        if dlg.exec():
            self._on_account_signed_in()

    def _on_account_signed_in(self) -> None:
        data = self.accounts.apply_to_browser()
        if data.get("settings"):
            patch = {k: v for k, v in data["settings"].items() if v is not None}
            if patch:
                self.settings.update(patch)
                save_json(SETTINGS_PATH, self.settings)
                self._apply_settings(patch)
        if data.get("bookmarks"):
            self.bookmarks = data["bookmarks"]
            save_json(BOOKMARKS_PATH, self.bookmarks)
        name = data.get("profile", {}).get("display_name") or self.accounts.username
        if name:
            self.settings["user_name"] = str(name)[:40]
            self.ai_panel.set_user_name(self.settings["user_name"])
        self._sync_account_now()
        self.statusBar().showMessage(f"Signed in as {self.accounts.username} — syncing saved data", 5000)
        self._start_html_cache = ""

    def _sync_account_now(self) -> None:
        if not self.accounts.logged_in:
            return
        self.accounts.sync_from_browser(
            bookmarks=self.bookmarks,
            settings=self.settings,
            profile={"display_name": self.settings.get("user_name", "Josh")},
        )

    def _show_account_menu(self) -> None:
        pos = self.account_btn.mapToGlobal(self.account_btn.rect().bottomLeft())
        self._account_menu.exec(pos)

    def _populate_account_menu(self) -> None:
        self._account_menu.clear()
        if self.accounts.logged_in:
            head = self._account_menu.addAction(f"Signed in: {self.accounts.username}")
            head.setEnabled(False)
            self._account_menu.addSeparator()
            pw = self._account_menu.addAction("Saved passwords…")
            pw.triggered.connect(self._show_saved_passwords)
            sync = self._account_menu.addAction("Sync now")
            sync.triggered.connect(self._sync_account_now)
            save_pw = self._account_menu.addAction("Save password for this page…")
            save_pw.triggered.connect(self._save_password_for_page)
            out = self._account_menu.addAction("Sign out")
            out.triggered.connect(self._account_sign_out)
        else:
            inn = self._account_menu.addAction("Sign in / Create account")
            inn.triggered.connect(lambda: self.show_login_dialog())
            hint = self._account_menu.addAction("Optional — saves bookmarks & passwords on this PC")
            hint.setEnabled(False)

    def _account_sign_out(self) -> None:
        self.accounts.logout()
        self.statusBar().showMessage("Signed out", 3000)

    def _save_password_for_page(self) -> None:
        if not self.accounts.logged_in:
            self.show_login_dialog()
            return
        v = self.current_view()
        if not v:
            return
        site = v.url().toString()
        if site.startswith("lumen://"):
            QMessageBox.information(self, "Save password", "Open a website first.")
            return
        user, ok1 = QInputDialog.getText(self, "Save password", "Username / email:")
        if not ok1 or not user.strip():
            return
        pw, ok2 = QInputDialog.getText(self, "Save password", "Password:", QLineEdit.EchoMode.Password)
        if not ok2 or not pw:
            return
        self.accounts.save_password(site, user.strip(), pw)
        self._sync_account_now()
        self.statusBar().showMessage("Password saved to your account", 4000)

    def _show_saved_passwords(self) -> None:
        items = self.accounts.list_passwords()
        if not items:
            QMessageBox.information(self, "Saved passwords", "No saved passwords yet.")
            return
        lines = []
        for p in items[:15]:
            lines.append(f"{p.get('site', '?')}\n  User: {p.get('username', '')}")
        QMessageBox.information(self, "Saved passwords", "\n\n".join(lines))

    def _configure_assistant_brain(self) -> None:
        name = self.settings.get("user_name", "Josh")
        self.ai_panel.assistant.configure(
            user_name=name,
            ai_provider=self.settings.get("ai_provider", "builtin"),
            lumen_ai_url=self.settings.get("lumen_ai_url", ""),
            lumen_client_token=self.settings.get("lumen_client_token", ""),
            openai_api_key=self.settings.get("openai_api_key", ""),
            openai_model=self.settings.get("openai_model", "gpt-4o-mini"),
            use_ollama=self.settings.get("use_ollama", False),
        )
        if self.settings.get("use_ollama", False) or self.settings.get("ai_provider") == "ollama":
            self.ai_panel.assistant.refresh_ollama()
        label, model = self.ai_panel.assistant.chat_status()
        self.ai_panel.set_ai_status(label, self.ai_panel.assistant.chat_ready(), model)

    def _init_assistant_brain(self) -> None:
        name = self.settings.get("user_name", "Josh")
        self.ai_panel.set_user_name(name)
        self._configure_assistant_brain()
        self.statusBar().showMessage(
            'LUMEN Mind ready — free unlimited knowledge — say "Lumen" to talk',
            8000,
        )

    def _position_side_panels(self) -> None:
        if not hasattr(self, "browser_container"):
            return
        r = self.browser_container.rect()
        for panel in (self.settings_panel, self.ai_panel):
            if panel.isVisible():
                pw = panel.width()
                panel.setGeometry(max(0, r.width() - pw), 0, pw, r.height())
                panel.raise_()

    def _build_shortcuts(self) -> None:
        shortcuts = [
            ("Ctrl+T", lambda: self.add_tab()),
            ("Ctrl+W", self._close_current_tab),
            ("Ctrl+L", lambda: self.omnibox.setFocus()),
            ("Ctrl+R", self._reload),
            ("Ctrl+Shift+A", self._toggle_ai),
            ("Ctrl+Shift+V", self._on_bubble_listen),
            ("F12", self._toggle_devtools),
            ("Ctrl+Shift+I", self._toggle_devtools),
            ("Ctrl+Shift+C", lambda: self._open_devtools(pick=True)),
            ("Ctrl+Q", self.close),
        ]
        for seq, fn in shortcuts:
            a = QAction(self)
            a.setShortcut(QKeySequence(seq))
            a.triggered.connect(fn)
            self.addAction(a)

    def apply_theme(self) -> None:
        self.colors = load_theme(self.settings.get("theme", "edge-jazz"))
        QApplication.instance().setStyleSheet(global_stylesheet(self.colors))
        self.title_bar.set_colors(self.colors)
        self._style_chrome()
        self._start_html_cache = ""

    def _session_stats(self) -> dict:
        s = get_shields().stats
        return {
            "ads": s.ads_blocked,
            "threats": s.threats_blocked,
            "vpn_kb": self.vpn.get_status().bytes_tunneled // 1024,
        }

    def _toggle_settings(self) -> None:
        opening = not self.settings_panel.isVisible()
        if opening:
            self.ai_panel.hide()
            self.settings_panel.update_stats(self._session_stats())
        self.settings_panel.setVisible(opening)
        if opening:
            self._position_side_panels()

    def _toggle_ai(self) -> None:
        opening = not self.ai_panel.isVisible()
        if opening:
            self.settings_panel.hide()
            v = self.current_view()
            if v:
                ctx = PageContext(url=v.url().toString(), title=v.title() or "")
                self.ai_panel.set_page_context(ctx)
                self.ai_panel.set_context_hint(ctx)
        self.ai_panel.setVisible(opening)
        if opening:
            self._position_side_panels()
            QTimer.singleShot(300, self._refresh_ai_context_lazy)

    def _open_ai_panel(self) -> None:
        if self.ai_panel.isVisible():
            return
        self.settings_panel.hide()
        v = self.current_view()
        if v:
            ctx = PageContext(url=v.url().toString(), title=v.title() or "")
            self.ai_panel.set_page_context(ctx)
        self.ai_panel.setVisible(True)
        self._position_side_panels()
        QTimer.singleShot(300, self._refresh_ai_context_lazy)

    def _bring_to_front(self) -> None:
        if self.isMinimized() or not self.isVisible():
            self.showNormal()
        self.raise_()
        self.activateWindow()
        try:
            import ctypes
            ctypes.windll.user32.SetForegroundWindow(int(self.winId()))
        except (AttributeError, OSError, ValueError):
            pass

    def _position_mind_bubble(self) -> None:
        if hasattr(self, "mind_bubble"):
            self.mind_bubble.sync_to_anchor()
            self.mind_bubble.raise_()

    def _page_context(self) -> PageContext:
        v = self.current_view()
        if v:
            return PageContext(url=v.url().toString(), title=v.title() or "")
        return PageContext()

    def _open_settings_voice(self) -> None:
        if not self.settings_panel.isVisible():
            self._toggle_settings()
        self._position_side_panels()
        self.statusBar().showMessage("Settings opened.", 3000)

    def _read_page_aloud(self) -> None:
        v = self.current_view()
        if not v:
            speak_reply("No page is open.", on_done=None)
            return
        title = v.title() or "this page"
        msg = f"Current page: {title}."
        if self.settings.get("spoken_replies", True):
            self.voice.notify_tts_start(greeting=False)
            speak_reply(msg, on_done=lambda: QTimer.singleShot(0, self._on_spoken_reply_done))
        else:
            self.statusBar().showMessage(msg, 5000)

    def _app_voice_action(self, payload: str) -> None:
        if payload == "settings":
            self._open_settings_voice()
            announce("Settings opened.", enabled=self.settings.get("accessibility_announcements", True))
        elif payload == "read_page":
            self._read_page_aloud()
        elif payload == "sleep":
            self.statusBar().showMessage('Say "Lumen" when you need me.', 5000)
            announce("Going to sleep.", enabled=self.settings.get("accessibility_announcements", True))
        elif payload.startswith("reminder:"):
            task = payload.split(":", 1)[-1]
            self.ai_panel.assistant._memory.remember_fact(f"Reminder: {task}")
            reply = f"Reminder saved: {task}"
            self.statusBar().showMessage(reply, 5000)
            if self.settings.get("spoken_replies", True):
                speak_reply(reply, on_done=lambda: QTimer.singleShot(0, self._on_spoken_reply_done))

    def _on_voice_confirm(self, text: str) -> None:
        if not self.settings.get("confirm_low_confidence", True):
            return
        msg = confirm_question(text)
        self.statusBar().showMessage(msg, 6000)
        if self.settings.get("spoken_replies", True):
            self.voice.notify_tts_start(greeting=False)
            speak_reply(
                msg,
                on_done=lambda: QTimer.singleShot(0, self.voice.notify_tts_finished),
            )

    def _voice_is_busy(self) -> bool:
        return (
            self._voice_processing
            or self.voice.is_assistant_busy()
            or (self._assistant_worker is not None and self._assistant_worker.isRunning())
        )

    def _handle_assistant_input(self, text: str, *, from_voice: bool = False) -> None:
        session = get_session()
        text = voice_transcript(normalize_command(text.strip()))
        text = session.expand_followup(text)
        shortcut = self.ai_panel.assistant._memory.match_shortcut(text)
        if shortcut:
            text = shortcut
        if not looks_like_question(text):
            text = sanitize_command(text)
        if not text or is_wake_only(text) or is_tts_garbage(text):
            if from_voice:
                self.voice.set_assistant_busy(False)
                self.voice.resume_listening()
                self.mind_bubble.set_listening()
            return
        if not from_voice and not looks_like_command(text):
            return
        if not from_voice and self._assistant_worker and self._assistant_worker.isRunning():
            mark("assistant.busy_drop", text=text[:40])
            return

        ctx = self._page_context()
        self.ai_panel.set_page_context(ctx)
        name = self.settings.get("user_name", "Josh")
        self.mind_bubble.set_query(text)
        if from_voice:
            session.begin()
            self.voice.set_assistant_busy(True)

        # Browser commands only — everything else uses free knowledge (Wikipedia / web)
        with perf_span("intent.resolve", slow_ms=15.0):
            use_browser = should_use_browser_intent(text, ctx.url, ctx.title)
            intent = resolve_intent(text, ctx.url, ctx.title) if use_browser else None
        if intent:
            self._apply_assistant_result(
                text,
                intent.reply,
                AssistantAction(intent.kind, intent.payload),
                from_voice=from_voice,
            )
            return

        # Slow path — knowledge / Ollama / fallback (background thread)
        self._voice_processing = from_voice
        self.mind_bubble.set_processing()
        self.statusBar().showMessage("Thinking…", 3000)
        worker = AssistantWorker(
            self.ai_panel.assistant,
            text,
            ctx,
            user_name=name,
        )
        self._assistant_worker = worker
        worker.finished_ok.connect(
            lambda t, reply, action, fv=from_voice: self._apply_assistant_result(
                t, reply, action, from_voice=fv, skip_memory=True,
            )
        )
        worker.failed.connect(self._on_assistant_failed)
        worker.start()

    def _apply_assistant_result(
        self,
        text: str,
        reply: str,
        action: AssistantAction | None,
        *,
        from_voice: bool = False,
        skip_memory: bool = False,
    ) -> None:
        self._voice_processing = False
        if not skip_memory:
            self.ai_panel.assistant._memory.add_turn(text, reply)
        session = get_session()
        session.record(
            text,
            reply,
            action=action.kind if action else "",
            target=action.payload[:80] if action and action.payload else "",
        )
        self.ai_panel.record_exchange(text, reply, user_already_shown=not from_voice)
        self.mind_bubble.set_query(text, subtitle=reply[:72])

        if action:
            if action.kind == "summarize":
                self._ai_summarize(speak_result=from_voice)
            elif action.kind == "app":
                self._app_voice_action(action.payload)
            else:
                self._ai_action(action.kind, action.payload)

        self.statusBar().showMessage(reply[:120], 5000)

        if from_voice and self.settings.get("spoken_replies", True) and reply:
            self.mind_bubble.set_speaking()
            self.voice.notify_tts_start(greeting=False)
            speak_reply(reply, on_done=lambda: QTimer.singleShot(0, self._on_spoken_reply_done))
        elif from_voice:
            self.voice.set_assistant_busy(False)
            self.voice.resume_listening()
            self.mind_bubble.set_listening()
            self.statusBar().showMessage("Listening… say your next command.", 3500)
        else:
            self.mind_bubble.set_listening()

    def _on_assistant_failed(self, text: str, error: str) -> None:
        self._voice_processing = False
        mark("assistant.error", err=error[:80])
        self.statusBar().showMessage(f"Assistant error: {error[:80]}", 6000)
        self.voice.set_assistant_busy(False)
        self.voice.resume_listening()
        self.mind_bubble.set_listening()

    def _on_spoken_reply_done(self) -> None:
        self.voice.notify_tts_finished()
        self.voice.set_assistant_busy(False)
        self.mind_bubble.set_listening()
        self.statusBar().showMessage("Listening… say your next command.", 3500)

    def _on_voice_partial(self, text: str) -> None:
        self.mind_bubble.set_partial(text)

    def _on_mic_health(self, energy: float, threshold: float) -> None:
        if energy > 0 and energy < threshold * 0.45:
            self.statusBar().showMessage("Mic level low — speak closer or check input device.", 2500)

    def _execute_voice_command(self, text: str) -> None:
        self._handle_assistant_input(text, from_voice=True)

    def _on_speech_started(self) -> None:
        self._position_mind_bubble()
        self.mind_bubble.set_listening()

    def _on_command_listen(self) -> None:
        self._position_mind_bubble()
        self.mind_bubble.set_listening()

    def _on_bubble_listen(self) -> None:
        """Click orb or Ctrl+Shift+V — listen for command without wake word."""
        if not self.settings.get("voice_control", True):
            return
        self._bring_to_front()
        self._position_mind_bubble()
        self.mind_bubble.set_listening()
        self.statusBar().showMessage('Listening — say "open youtube", "open maps", etc.', 5000)

        def _start_listen() -> None:
            self.voice.listen_for_command()

        speak_ack(on_done=lambda: QTimer.singleShot(0, _start_listen))

    def _on_hey_mind(self, skip_greeting: bool = False) -> None:
        name = self.settings.get("user_name", "Josh")
        self._position_mind_bubble()
        self.mind_bubble.set_wake(name)
        self.statusBar().showMessage(f"At your service, {name}.", 5000)

        if skip_greeting:
            QTimer.singleShot(0, self._on_greeting_finished)
            return

        self.voice.notify_tts_start(greeting=True)
        greet_user(name, on_done=lambda: QTimer.singleShot(0, self._on_greeting_finished))

    def _on_greeting_finished(self) -> None:
        self.voice.on_greeting_finished()
        self._position_mind_bubble()
        self.mind_bubble.set_listening()
        self.statusBar().showMessage("Listening… say your next command.", 4000)

    def _on_voice_speech(self, text: str) -> None:
        if is_wake_only(text) or is_tts_garbage(text):
            return
        # Defer to next event-loop tick — avoids races with voice worker commit.
        QTimer.singleShot(0, lambda t=text: self._dispatch_voice_command(t))

    def _prompt_grocery_item(self, prefix: str) -> None:
        """User said only 'search' — wait for the item name on the next utterance."""
        session = get_session()
        session.pending_prefix = prefix.strip().lower()
        session.record(prefix, "Say the item name.", action="grocery_pending")
        session.extend(45.0)
        label = "Search Tesco" if prefix.startswith("search") else prefix.title()
        self.mind_bubble.set_query(label, subtitle="Say the item — e.g. spaghetti, milk…")
        self.statusBar().showMessage("Say the item name — e.g. spaghetti, milk, bread", 6000)
        _log_voice_app(f"pending grocery: {prefix!r}")
        self.voice.set_assistant_busy(False)
        self.voice.resume_listening()

    def _dispatch_voice_command(self, raw: str) -> None:
        """Run browser commands immediately when heard — never silently drop."""
        try:
            self._dispatch_voice_command_impl(raw)
        except Exception as exc:
            _log_voice_app(f"dispatch error: {exc!r}")
            self.statusBar().showMessage("Command error — try again.", 5000)
            self.voice.set_assistant_busy(False)
            self.voice.resume_listening()
            self.mind_bubble.set_listening()

    def _dispatch_voice_command_impl(self, raw: str) -> None:
        text = voice_transcript(normalize_command(raw.strip()))
        text = get_session().expand_followup(text)
        if not text or is_wake_only(text) or is_tts_garbage(text):
            _log_voice_app(f"drop {raw!r}")
            self.voice.set_assistant_busy(False)
            self.voice.resume_listening()
            return

        from ui.command_sanitize import expand_grocery_command, expand_scroll_command, is_grocery_prefix_only
        cleaned = sanitize_command(text) if not looks_like_question(text) else text
        if not looks_like_question(cleaned):
            scroll_ctx = self._auto_scrolling or get_session().last_action == "scroll"
            cleaned = expand_scroll_command(cleaned, scroll_context=scroll_ctx)
        if is_grocery_prefix_only(cleaned):
            self._prompt_grocery_item(cleaned)
            return
        get_session().pending_prefix = ""
        if not looks_like_question(cleaned):
            cleaned = expand_grocery_command(cleaned)
        fast = match_fast_command(cleaned)
        if fast and fast.kind in _FAST_VOICE_KINDS:
            _log_voice_app(f"fast {fast.kind}: {cleaned!r}")
            self._execute_voice_intent(cleaned, fast)
            return

        ctx = self._page_context()
        if should_use_browser_intent(cleaned, ctx.url, ctx.title):
            intent = resolve_intent(cleaned, ctx.url, ctx.title)
            if intent and intent.kind in _FAST_VOICE_KINDS:
                _log_voice_app(f"intent {intent.kind}: {cleaned!r}")
                self._execute_voice_intent(cleaned, intent)
                return

        _log_voice_app(f"assistant: {cleaned!r}")
        self._handle_assistant_input(raw, from_voice=True)

    def _execute_voice_intent(self, text: str, intent: IntentResult) -> None:
        """Execute a voice command now with visible feedback."""
        self._voice_processing = False
        if intent.kind == "scroll":
            self.mind_bubble.set_query(text, subtitle=intent.reply[:72])
            _log_voice_app(f"exec scroll -> {intent.payload}")
            self._scroll_control(intent.payload)
            get_session().record(text, intent.reply, action="scroll", target=intent.payload)
            self.voice.set_assistant_busy(False)
            self.voice.resume_listening()
            self.mind_bubble.set_listening()
            self.statusBar().showMessage(intent.reply[:120], 5000)
            return
        self.voice.set_assistant_busy(True)
        self.mind_bubble.set_query(text, subtitle=intent.reply[:72])
        self.raise_()
        self.activateWindow()
        v = self.current_view()
        if v:
            v.setFocus()
        action = AssistantAction(intent.kind, intent.payload)
        _log_voice_app(f"exec {action.kind} -> {action.payload[:80]}")
        self._apply_assistant_result(text, intent.reply, action, from_voice=True)

    def _voice_command(self) -> None:
        if self.settings.get("voice_control", True):
            self.voice.listen_for_command()

    def _on_voice_status(self, text: str) -> None:
        if text == "At your service…":
            name = self.settings.get("user_name", "Josh")
            self._position_mind_bubble()
            self.mind_bubble.set_wake(name)
            self.statusBar().showMessage(f"At your service, {name}.", 5000)
        if self.ai_panel.isVisible():
            self.ai_panel.set_voice_status(text)

    def _on_voice_error(self, msg: str) -> None:
        self.statusBar().showMessage(msg, 6000)

    def _on_voice_debug(self, text: str) -> None:
        pass

    def _on_mic_level(self, level: float) -> None:
        self.mind_bubble.set_voice_level(level)

    def _on_mic_available(self, ok: bool) -> None:
        if ok:
            name = self.settings.get("user_name", "Josh")
            prewarm_greeting(name)
            self.mind_bubble.show_idle()
            self.statusBar().showMessage(
                'Say "Lumen" — instant greeting, then speak your command.',
                7000,
            )
        else:
            self.statusBar().showMessage("Mic unavailable — check Windows microphone settings", 6000)

    def _accept_cookies_on_page(self, view: BrowserTab) -> None:
        if not self.settings.get("auto_accept_cookies", True):
            return
        u = view.url().toString()
        if u.startswith("lumen://") or not u.startswith("http"):
            return
        view.page().runJavaScript(COOKIE_DISMISS_JS)
        QTimer.singleShot(1500, lambda v=view: v.page().runJavaScript(COOKIE_DISMISS_JS))
        QTimer.singleShot(3500, lambda v=view: v.page().runJavaScript(COOKIE_DISMISS_JS))

    def _resume_voice_after_load(self) -> None:
        pass

    def _start_voice(self) -> None:
        if not self.settings.get("voice_control", True):
            return
        if not VoiceEngine.is_supported():
            self.statusBar().showMessage(
                "Voice: run pip install SpeechRecognition sounddevice numpy", 8000
            )
            return
        if not self.voice.start():
            return
        self.voice.set_confirm_enabled(self.settings.get("confirm_low_confidence", True))
        name = self.settings.get("user_name", "Josh")
        prewarm_greeting(name)
        self.statusBar().showMessage(
            'LUMEN Mind listening — say "Lumen"', 6000
        )

    def _refresh_ai_context_lazy(self) -> None:
        """Load page text in background — never blocks panel open."""
        if not self.ai_panel.isVisible():
            return
        v = self.current_view()
        if not v:
            return
        url = v.url().toString()
        if url.startswith("lumen://"):
            return
        ctx = self.ai_panel._context

        def on_text(result) -> None:
            if result and isinstance(result, str):
                ctx.body_text = result[:2000]
                self.ai_panel.set_page_context(ctx)

        v.page().runJavaScript(
            "(document.body&&document.body.innerText||'').slice(0,2000)",
            on_text,
        )

    def _refresh_ai_context(self) -> None:
        v = self.current_view()
        if not v:
            return
        ctx = PageContext(url=v.url().toString(), title=v.title() or "")
        self.ai_panel.set_page_context(ctx)
        self.ai_panel.set_context_hint(ctx)
        if self.ai_panel.isVisible():
            QTimer.singleShot(100, self._refresh_ai_context_lazy)

    def _ai_action(self, kind: str, payload: str) -> None:
        if kind == "new_tab":
            self.add_tab()
        elif kind == "back":
            v = self.current_view()
            if v:
                v.back()
        elif kind == "forward":
            v = self.current_view()
            if v:
                v.forward()
        elif kind == "reload":
            self._reload()
        elif kind == "summarize":
            self._ai_summarize()
        elif kind == "media":
            self._media_control(payload)
        elif kind == "scroll":
            self._scroll_control(payload)
        elif kind == "grocery":
            self._grocery_control(payload)
        elif kind == "search":
            eng = self.settings.get("search_engine", "duckduckgo")
            _, tpl = FREE_ENGINES.get(eng, FREE_ENGINES["duckduckgo"])
            url = tpl.format(quote(payload))
            v = self.current_view()
            if v:
                v.load(QUrl(url))
        elif kind == "navigate":
            url = payload if payload.startswith(("http://", "https://")) else self._normalize(payload)
            v = self.current_view()
            if v:
                is_threat, reason = get_shields().check_threat(url)
                if is_threat and self.settings.get("firewall", True):
                    get_shields().record_threat_block()
                    v.setHtml(threat_block_html(url, reason, self.colors), QUrl("lumen://blocked"))
                else:
                    self._navigate_with_feedback(v, url)
        QTimer.singleShot(800, self._refresh_ai_context)

    def _navigate_with_feedback(self, v: BrowserTab, url: str, *, label: str = "") -> None:
        """Navigate with immediate UI feedback so voice actions are always visible."""
        url = url if url.startswith(("http://", "https://")) else self._normalize(url)
        self.omnibox.setText(url)
        self.mind_bubble.set_query(label or "Opening…", subtitle=url[:72])
        self.raise_()
        self.activateWindow()
        if is_retail_grocery_url(url):
            _log_voice_app(f"retail edge: {url}")
            QTimer.singleShot(0, lambda u=url, lb=label: self.add_retail_tab(u, label=lb))
            return
        v.setFocus()
        v.load(QUrl(url))

    def add_retail_tab(self, url: str, *, label: str = "") -> None:
        """Open grocery sites in Microsoft Edge (separate process) — safe + passes Akamai."""
        store = "Tesco" if "tesco" in url.lower() else "Groceries"
        if label and "tesco" in label.lower():
            store = "Tesco"

        try:
            opened = open_grocery_in_edge(url)
        except Exception as exc:
            _log_voice_app(f"edge launch error: {exc}")
            opened = open_system_browser(url)

        _log_voice_app(f"retail edge process: {opened} {url}")
        msg = f"{store} is open in Microsoft Edge."
        self.omnibox.setText(url)
        self.mind_bubble.set_query(f"Open {store}", subtitle="Say search and an item for Tesco")
        self.statusBar().showMessage(msg, 8000)

        v = self.current_view()
        if v and not EDGE_TAB_AVAILABLE:
            hint = (
                f"<html><body style='font-family:Segoe UI,sans-serif;padding:48px;"
                f"background:{self.colors['bg0']};color:{self.colors['text']}'>"
                f"<h2>{store} is open in Microsoft Edge</h2>"
                f"<p>Akamai blocks LUMEN's built-in browser for grocery sites.</p>"
                f"<p>Say <b>search spaghetti</b> (or any item) to search Tesco in Edge.</p>"
                f"</body></html>"
            )
            v.setHtml(hint, QUrl("lumen://edge-shop"))

    def _grocery_js_result(
        self, item: str, action: str, attempt: int, result: object | None,
    ) -> None:
        result_str = str(result or "")
        _log_voice_app(f"grocery result {item!r}: {result_str[:60]!r}")
        if not result_str and attempt == 0:
            self.statusBar().showMessage(
                "Couldn't reach Edge — make sure the Tesco window from LUMEN is still open.",
                6000,
            )
        if result_str.startswith("search"):
            self.statusBar().showMessage(f"Showing Tesco results for {item}", 5000)
            self.mind_bubble.set_query(f"Search {item}", subtitle="Results on Tesco")
            return
        if result_str.startswith("added"):
            self.statusBar().showMessage(f"Added {item} to basket", 5000)
            self.mind_bubble.set_query(f"Added {item}", subtitle="In your basket")
            return
        if attempt < 14:
            delay = 2000 + attempt * 450 if result_str.startswith("search") else 700 + attempt * 350
            QTimer.singleShot(delay, lambda: self._grocery_control(action, attempt=attempt + 1))
            return
        self.statusBar().showMessage(
            f"Couldn't add {item} automatically — search for it on the Tesco page in Edge.",
            6000,
        )

    def _run_grocery_js(self, js: str, item: str, action: str, attempt: int, *, use_edge: bool) -> None:
        if use_edge:
            _log_voice_app(f"edge grocery js: {item!r} attempt={attempt}")

            def _worker() -> None:
                result = edge_eval_grocery(js, url_hint="tesco")
                QTimer.singleShot(
                    0,
                    lambda r=result: self._grocery_js_result(item, action, attempt, r),
                )

            threading.Thread(target=_worker, daemon=True).start()
            return

        v = self.current_view()
        if v:
            v.page().runJavaScript(js, lambda r: self._grocery_js_result(item, action, attempt, r))

    def _grocery_control(self, action: str, *, attempt: int = 0) -> None:
        from ui.grocery_control import (
            GROCERY_STORES,
            add_item_js,
            is_grocery_url,
            normalize_item,
            open_basket_js,
        )

        v = self.current_view()
        if not v:
            return
        v.setFocus()
        url = v.url().toString()
        use_edge = edge_is_active() or url.startswith("lumen://edge") or "edge-shop" in url

        if action.startswith("open:"):
            store = action.split(":", 1)[1]
            target = GROCERY_STORES.get(store, GROCERY_STORES.get("tesco", "https://www.tesco.com/groceries/"))
            self._navigate_with_feedback(v, target, label=f"Opening {store.title()}")
            self.statusBar().showMessage(f"Opening {store.title()}", 4000)
            return

        if action == "basket":
            if not is_grocery_url(url) and not use_edge:
                self.statusBar().showMessage("Open a grocery site first — say open Tesco.", 5000)
                return
            self._run_grocery_js(open_basket_js(), "basket", action, attempt, use_edge=use_edge)
            self.statusBar().showMessage("Opening your basket", 3000)
            return

        if action.startswith("search:"):
            item = normalize_item(action.split(":", 1)[1])
            if attempt == 0:
                self.statusBar().showMessage(f"Searching Tesco for {item}…", 3000)
                self.mind_bubble.set_query(f"Search {item}", subtitle="Opening Tesco search in Edge…")
            _log_voice_app(f"edge search tesco: {item!r} attempt={attempt}")

            def _search_worker() -> None:
                ok = edge_search_tesco(item)
                result = "search-navigated" if ok else ""
                QTimer.singleShot(
                    0,
                    lambda r=result: self._grocery_js_result(item, action, attempt, r),
                )

            threading.Thread(target=_search_worker, daemon=True).start()
            return

        if not action.startswith("add:"):
            return

        item = normalize_item(action.split(":", 1)[1])
        if not is_grocery_url(url) and not use_edge:
            if attempt == 0:
                self._navigate_with_feedback(
                    v, GROCERY_STORES["tesco"], label=f"Opening Tesco to add {item}",
                )
                self.statusBar().showMessage(f"Opening Tesco to add {item}…", 4000)
                self.mind_bubble.set_query(f"Add {item}", subtitle="Opening Tesco…")
                QTimer.singleShot(2800, lambda: self._grocery_control(action, attempt=attempt + 1))
            return

        add_only = attempt > 0
        js = add_item_js(item, add_only=add_only)
        if attempt == 0:
            self.statusBar().showMessage(f"Adding {item}…", 3000)
            self.mind_bubble.set_query(f"Add {item}", subtitle="Searching in Edge…")
        self._run_grocery_js(js, item, action, attempt, use_edge=use_edge or edge_is_active())

    def _scroll_control(self, action: str) -> None:
        """Slow auto-scroll on the current page (LUMEN tab or Edge Tesco)."""
        from ui.scroll_control import scroll_js_for_action, scroll_status_message

        v = self.current_view()
        url = v.url().toString() if v else ""
        use_edge = edge_is_active() or url.startswith("lumen://edge") or "edge-shop" in url

        if not use_edge and (not v or url.startswith("lumen://")):
            self.statusBar().showMessage("Open a webpage first, then say scroll.", 5000)
            self._auto_scrolling = False
            return

        js = scroll_js_for_action(action)
        status, subtitle = scroll_status_message(action)
        if action == "stop":
            self._auto_scrolling = False
            self.mind_bubble.set_query("Stop", subtitle=subtitle)
        elif action == "nudge_up":
            self._auto_scrolling = False
            self.mind_bubble.set_query("Scroll up", subtitle=subtitle)
        else:
            self._auto_scrolling = True
            self.mind_bubble.set_query("Scroll", subtitle=subtitle)
        self.statusBar().showMessage(status, 4000 if action == "nudge_up" else 8000)

        if use_edge:
            def _worker() -> None:
                try:
                    edge_eval_page(js, prefer="tesco")
                except Exception as exc:
                    _log_voice_app(f"edge scroll js error: {exc!r}")

            threading.Thread(target=_worker, daemon=True).start()
        elif v:
            v.setFocus()
            v.page().runJavaScript(js)

    def _media_control(self, action: str, *, attempt: int = 0) -> None:
        v = self.current_view()
        if not v:
            return
        v.setFocus()
        js = MEDIA_CONTROL_JS.get(action)
        if not js and action.startswith("video_"):
            try:
                from ui.media_control import _video_at_index_js
                js = _video_at_index_js(int(action.split("_", 1)[1]))
            except (ValueError, IndexError):
                js = MEDIA_CONTROL_JS.get("video_1")
        if not js:
            js = MEDIA_CONTROL_JS["pause"]

        labels = {
            "pause": "Paused",
            "play": "Playing",
            "stop": "Stopped",
            "mute": "Muted",
            "unmute": "Unmuted",
            "volume_up": "Volume up",
            "volume_down": "Volume down",
            "first_video": "First video",
            "video_1": "First video",
            "video_2": "Second video",
            "video_3": "Third video",
            "video_4": "Fourth video",
            "video_5": "Fifth video",
        }

        def _on_js_result(result) -> None:
            result_str = str(result or "")
            failed = not result_str or result_str.startswith("none")
            if failed and attempt < 8 and action.startswith("video_"):
                delay = 400 + attempt * 350
                QTimer.singleShot(delay, lambda: self._media_control(action, attempt=attempt + 1))
                return
            if not failed and action.startswith("video_"):
                self.statusBar().showMessage(labels.get(action, "Video opened"), 3000)
                self.mind_bubble.set_query(labels.get(action, action), subtitle=labels.get(action, action))
            elif failed and attempt >= 8:
                self.statusBar().showMessage("Could not find that video — try scrolling the page.", 5000)

        v.page().runJavaScript(js, _on_js_result)
        if attempt == 0:
            self.statusBar().showMessage(labels.get(action, "Working…"), 2000)

    def _ai_summarize(self, *, speak_result: bool = False) -> None:
        v = self.current_view()
        if not v or v.url().toString().startswith("lumen://"):
            msg = "Open a webpage first, then ask me to summarize."
            self.ai_panel.show_summary(msg)
            if speak_result:
                self.voice.notify_tts_start(greeting=False)
                speak_reply(
                    msg,
                    on_done=lambda: QTimer.singleShot(0, self._on_spoken_reply_done),
                )
            return

        def on_text(result) -> None:
            try:
                import json as _json
                data = _json.loads(result) if result else {}
            except (_json.JSONDecodeError, TypeError):
                data = {}
            text = data.get("text", "")
            summary = self.ai_panel.assistant.summarize_text(text)
            self.ai_panel.show_summary(summary)
            self.mind_bubble.set_query("Summary", subtitle=summary[:60])
            if speak_result and self.settings.get("spoken_replies", True):
                self.voice.notify_tts_start(greeting=False)
                speak_reply(
                    summary,
                    on_done=lambda: QTimer.singleShot(0, self._on_spoken_reply_done),
                )

        js = """JSON.stringify({
            text: (document.body && document.body.innerText || '').slice(0, 8000),
            title: document.title || ''
        })"""
        v.page().runJavaScript(js, on_text)

    def _open_devtools(self, view: BrowserTab | None = None, pick: bool = False) -> None:
        v = view or self.current_view()
        if not v:
            return
        if EDGE_TAB_AVAILABLE and isinstance(v, EdgeTab):
            self.statusBar().showMessage("DevTools not available on Edge shopping tabs.", 3000)
            return
        page = v.page()
        self.devtools_view.setPage(v._dev_page)
        if not self._devtools_visible:
            self._devtools_visible = True
            self.devtools_view.setVisible(True)
            h = max(400, self.browser_container.height())
            self.content_split.setSizes([int(h * 0.62), int(h * 0.38)])
        if pick:
            page.triggerAction(QWebEnginePage.WebAction.InspectElement)
        self.statusBar().showMessage(
            "DevTools open — click the picker (top-left) or Ctrl+Shift+C",
            2500,
        )

    def _toggle_devtools(self) -> None:
        v = self.current_view()
        if not v:
            return
        if self._devtools_visible:
            self._devtools_visible = False
            self.devtools_view.setVisible(False)
            self.content_split.setSizes([1000, 0])
            self.statusBar().showMessage("Developer tools closed", 1500)
        else:
            self._open_devtools(v, pick=False)

    def _apply_settings(self, patch: dict) -> None:
        self.settings.update(patch)
        save_json(SETTINGS_PATH, self.settings)
        shields = get_shields()
        shields.ad_block_enabled = patch.get("ad_block", True)
        shields.firewall_enabled = patch.get("firewall", True)
        shields.block_level = patch.get("block_level", "aggressive")
        if "theme" in patch:
            self.apply_theme()
        if "auto_clear_cookies" in patch:
            self._schedule_cookie_sweep()
        if "voice_control" in patch:
            if patch.get("voice_control", True):
                self._start_voice()
            else:
                self.voice.stop()
        if "confirm_low_confidence" in patch:
            self.voice.set_confirm_enabled(patch.get("confirm_low_confidence", True))
        if "user_name" in patch:
            self.ai_panel.set_user_name(patch.get("user_name", "Josh"))
        if any(k in patch for k in (
            "use_ollama", "user_name", "ai_provider", "lumen_ai_url",
            "lumen_client_token", "openai_api_key", "openai_model",
        )):
            self._configure_assistant_brain()
        self.statusBar().showMessage("Settings saved", 2000)
        self._sync_account_now()

    def _schedule_cookie_sweep(self) -> None:
        self._cookie_timer.stop()
        if not self.settings.get("auto_clear_cookies", False):
            return
        mins = random.randint(20, 30)
        self._cookie_timer.start(mins * 60 * 1000)

    def _privacy_sweep(self) -> None:
        if not self.settings.get("auto_clear_cookies", False):
            return
        store = self.profile.cookieStore()
        store.deleteAllCookies()
        self.profile.clearHttpCache()
        for view in self._views:
            view.page().runJavaScript(
                "try{localStorage.clear();sessionStorage.clear()}catch(e){}"
            )
        self.statusBar().showMessage("Privacy sweep complete — cookies & cache cleared", 4000)
        self._schedule_cookie_sweep()

    def add_tab(self, url: str | None = None) -> None:
        view = BrowserTab(self.profile, self)
        idx = self.tab_bar.addTab("New Tab")
        self._views.append(view)
        self.stack.addWidget(view)
        self.tab_bar.setCurrentIndex(idx)
        page = view.page()
        page.titleChanged.connect(lambda t, v=view: self._set_tab_title(v, t))
        page.urlChanged.connect(lambda u, v=view: self._on_url(v, u))
        page.loadStarted.connect(lambda v=view: self._loading(v, True))
        page.loadFinished.connect(lambda ok, v=view: self._loaded(v, ok))
        page.threat_blocked.connect(
            lambda u, r: self.statusBar().showMessage(f"Blocked: {r}", 4000)
        )
        target = url or self.settings.get("homepage", "lumen://start")
        if target == "lumen://start":
            if not self._start_html_cache:
                self._start_html_cache = self._start_page()
            view.setHtml(self._start_html_cache, QUrl("lumen://start"))
        else:
            view.load(QUrl(self._normalize(target)))

    def close_tab(self, index: int) -> None:
        if self.tab_bar.count() <= 1:
            return
        v = self._views[index]
        self.tab_bar.removeTab(index)
        self.stack.removeWidget(v)
        self._views.pop(index)
        v.deleteLater()

    def _close_current_tab(self) -> None:
        i = self.tab_bar.currentIndex()
        if i >= 0:
            self.close_tab(i)

    def current_view(self) -> BrowserTab | None:
        i = self.tab_bar.currentIndex()
        return self._views[i] if 0 <= i < len(self._views) else None

    def _normalize(self, text: str) -> str:
        text = text.strip()
        if not text:
            return "https://duckduckgo.com"
        if text.startswith(("http://", "https://")):
            return text
        if text.startswith("localhost") or text.startswith("127.0.0.1"):
            return "http://" + text
        if "." in text and " " not in text:
            return "https://" + text
        _, tpl = FREE_ENGINES.get(
            self.settings.get("search_engine", "duckduckgo"), FREE_ENGINES["duckduckgo"]
        )
        return tpl.format(quote(text))

    def _navigate(self) -> None:
        v = self.current_view()
        if v:
            url = self._normalize(self.omnibox.text())
            is_threat, reason = get_shields().check_threat(url)
            if is_threat and self.settings.get("firewall", True):
                get_shields().record_threat_block()
                v.setHtml(threat_block_html(url, reason, self.colors), QUrl("lumen://blocked"))
            else:
                v.load(QUrl(url))

    def _reload(self) -> None:
        v = self.current_view()
        if not v:
            return
        if v.page().isLoading():
            v.stop()
            self.reload_btn.set_icon_name("reload")
        else:
            v.reload()

    def _set_tab_title(self, view: BrowserTab, title: str) -> None:
        try:
            i = self._views.index(view)
        except ValueError:
            return
        t = (title[:24] + "…") if len(title) > 24 else (title or "New Tab")
        self.tab_bar.setTabText(i, t)
        if view is self.current_view():
            self.title_bar.set_title(t)

    def _on_url(self, view: BrowserTab, url: QUrl) -> None:
        u = url.toString()
        if view is self.current_view():
            self.omnibox.setText("" if u.startswith("lumen://") else u)
            self._sec_icon(u)
        view._last_active = time.time()
        view._hibernating = False

    def _loaded(self, view: BrowserTab, ok: bool) -> None:
        self._loading(view, False)
        retail_msg = on_retail_load_finished(
            view,
            self.profile,
            title=view.title(),
            url=view.url().toString(),
        )
        if retail_msg:
            self.statusBar().showMessage(retail_msg, 8000)
            if self.settings.get("spoken_replies", True):
                self.voice.notify_tts_start(greeting=False)
                speak_reply(retail_msg, on_done=lambda: QTimer.singleShot(0, self._on_spoken_reply_done))
        if ok:
            self._accept_cookies_on_page(view)
            if view is self.current_view():
                self._resume_voice_after_load()
        if view is self.current_view():
            self.back_btn.setEnabled(view.history().canGoBack())
            self.fwd_btn.setEnabled(view.history().canGoForward())
            u = view.url().toString()
            self.omnibox.setText("" if u.startswith("lumen://") else u)
            self._sec_icon(u)

    def _loading(self, view: BrowserTab, on: bool) -> None:
        try:
            i = self._views.index(view)
        except ValueError:
            return
        t = self.tab_bar.tabText(i).lstrip("· ")
        self.tab_bar.setTabText(i, f"· {t}" if on else t)
        if view is self.current_view():
            self.reload_btn.set_icon_name("stop" if on else "reload")

    def _on_tab_changed(self, index: int) -> None:
        if index < 0 or index >= len(self._views):
            return
        self.stack.setCurrentIndex(index)
        v = self._views[index]
        v._last_active = time.time()
        if v._hibernating and v._saved_url:
            v.load(QUrl(v._saved_url))
            v._hibernating = False
        u = v.url().toString()
        self.omnibox.setText("" if u.startswith("lumen://") else u)
        self.back_btn.setEnabled(v.history().canGoBack())
        self.fwd_btn.setEnabled(v.history().canGoForward())
        self._sec_icon(u)
        self.title_bar.set_title(v.title() or "")
        if self.devtools_view.isVisible():
            self.devtools_view.setPage(v._dev_page)
        if self.ai_panel.isVisible():
            ctx = PageContext(url=u, title=v.title() or "")
            self.ai_panel.set_page_context(ctx)
            self.ai_panel.set_context_hint(ctx)

    def _sec_icon(self, url: str) -> None:
        c = self.colors
        if url.startswith("https://"):
            self.secure_icon.setStyleSheet(
                f"background:{c['success']}; border-radius:4px; min-width:8px; min-height:8px;"
            )
        elif url.startswith("http://"):
            self.secure_icon.setStyleSheet(
                f"background:#c4a035; border-radius:4px; min-width:8px; min-height:8px;"
            )
        else:
            self.secure_icon.setStyleSheet(
                f"background:{c['text_muted']}; border-radius:4px; min-width:8px; min-height:8px;"
            )

    def _hibernate_inactive_tabs(self) -> None:
        if not self.settings.get("ram_saver", True):
            return
        limit = self.settings.get("hibernate_mins", 5) * 60
        now = time.time()
        cur = self.current_view()
        for v in self._views:
            if EDGE_TAB_AVAILABLE and isinstance(v, EdgeTab):
                continue
            if v is cur or v._hibernating:
                continue
            if now - v._last_active > limit:
                u = v.url().toString()
                if u and not u.startswith("lumen://"):
                    v._saved_url = u
                    v._hibernating = True
                    v.setHtml(
                        f"<html><body style='background:{self.colors['bg0']}'></body></html>",
                        QUrl("about:blank"),
                    )

    def _bookmark(self) -> None:
        v = self.current_view()
        if not v:
            return
        u = v.url().toString()
        if u.startswith("lumen://"):
            return
        entry = {"title": v.title() or u, "url": u}
        self.bookmarks = [b for b in self.bookmarks if b.get("url") != u]
        self.bookmarks.insert(0, entry)
        save_json(BOOKMARKS_PATH, self.bookmarks[:200])
        self._sync_account_now()
        self.statusBar().showMessage("Bookmark saved", 2000)

    def _show_bookmarks_menu(self) -> None:
        pos = self.bookmark_btn.mapToGlobal(self.bookmark_btn.rect().bottomLeft())
        self._bookmarks_menu.exec(pos)

    def _populate_bookmarks_menu(self) -> None:
        self._bookmarks_menu.clear()
        save_act = self._bookmarks_menu.addAction("Save current page")
        save_act.triggered.connect(self._bookmark)
        self._bookmarks_menu.addSeparator()
        if not self.bookmarks:
            empty = self._bookmarks_menu.addAction("No bookmarks yet")
            empty.setEnabled(False)
            return
        for bm in self.bookmarks[:25]:
            title = bm.get("title", bm.get("url", ""))[:48]
            url = bm.get("url", "")
            act = self._bookmarks_menu.addAction(title)
            act.triggered.connect(lambda _, u=url: self._open_bookmark(u))

    def _open_bookmark(self, url: str) -> None:
        v = self.current_view()
        if v:
            v.load(QUrl(url))

    def update_stats(self) -> None:
        s = self.vpn.get_status()
        sh = get_shields().stats
        self.statusBar().showMessage(
            f"  Protected  ·  VPN local/fast  ·  "
            f"{sh.ads_blocked:,} ads blocked  ·  "
            f"{sh.threats_blocked:,} threats blocked  ·  "
            f"{s.bytes_tunneled // 1024:,} KB"
        )
        if self.settings_panel.isVisible():
            self.settings_panel.update_stats(self._session_stats())

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange:
            QTimer.singleShot(0, self._position_mind_bubble)

    def closeEvent(self, event) -> None:
        if hasattr(self, "voice"):
            self.voice.stop()
        if self._assistant_worker and self._assistant_worker.isRunning():
            self._assistant_worker.wait(1500)
        try:
            self.ai_panel.assistant._memory.flush()
        except Exception:
            pass
        session_summary()
        super().closeEvent(event)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._position_side_panels()
        self._position_mind_bubble()

    def moveEvent(self, event) -> None:
        super().moveEvent(event)
        self._position_mind_bubble()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        QTimer.singleShot(0, self._position_side_panels)
        QTimer.singleShot(0, self._position_mind_bubble)

    def _start_page(self) -> str:
        c = self.colors
        jazz = c.get("jazz", c["primary"])
        return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>New tab</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{
  font-family:"Segoe UI Variable","Segoe UI",system-ui,sans-serif;
  background:{c['bg0']};color:{c['text']};
  min-height:100vh;display:flex;flex-direction:column;align-items:center;
  justify-content:center;padding:48px 24px;
}}
.search-wrap{{width:100%;max-width:560px}}
.search{{
  display:flex;align-items:center;background:{c['omnibox']};
  border:1px solid {c['border']};border-radius:4px;
  padding:0 4px 0 16px;height:44px;
  transition:border-color .15s;
}}
.search:focus-within{{border-color:{c['primary']}}}
input{{
  flex:1;background:transparent;border:none;outline:none;
  color:{c['text']};font-size:14px;
}}
input::placeholder{{color:{c['text_muted']}}}
button{{
  background:{c['primary']};color:#fff;border:none;border-radius:3px;
  padding:0 20px;height:34px;font-size:13px;cursor:pointer;font-weight:500;
}}
button:hover{{background:{jazz}}}
.links{{
  display:flex;flex-wrap:wrap;gap:8px;justify-content:center;
  margin-top:40px;max-width:560px;
}}
.links a{{
  color:{c['text_muted']};text-decoration:none;font-size:13px;
  padding:8px 14px;border-radius:4px;
}}
.links a:hover{{color:{c['text']};background:{c['bg2']}}}
.footer{{
  margin-top:48px;font-size:11px;color:{c['text_muted']};letter-spacing:0.3px;
}}
</style></head><body>
<div class="search-wrap">
  <form class="search" onsubmit="event.preventDefault();var q=q_input.value.trim();
    if(q)location='https://duckduckgo.com/?q='+encodeURIComponent(q)">
    <input id="q_input" placeholder="Search the web" autofocus>
    <button type="submit">Search</button>
  </form>
</div>
<div class="links">
  <a href="https://duckduckgo.com">DuckDuckGo</a>
  <a href="https://search.brave.com">Brave Search</a>
  <a href="https://wikipedia.org">Wikipedia</a>
  <a href="https://github.com">GitHub</a>
  <a href="https://news.ycombinator.com">Hacker News</a>
  <a href="lumen://login">Sign in</a>
</div>
<p class="footer">LUMEN · Private browsing · Cookies kept so you stay signed in</p>
</body></html>"""


def bootstrap_frozen() -> None:
    """Point Qt WebEngine at bundled binaries when running as EXE."""
    if not getattr(sys, "frozen", False):
        return
    exe_dir = Path(sys.executable).resolve().parent
    candidates = [
        Path(getattr(sys, "_MEIPASS", "")),
        exe_dir / "_internal",
        exe_dir,
    ]
    for base in candidates:
        if not base or not Path(base).exists():
            continue
        base = Path(base)
        qt6 = base / "PyQt6" / "Qt6"
        proc = qt6 / "bin" / "QtWebEngineProcess.exe"
        if proc.is_file():
            os.environ["QTWEBENGINEPROCESS_PATH"] = str(proc)
        resources = qt6 / "resources"
        if resources.is_dir():
            os.environ["QTWEBENGINE_RESOURCES_PATH"] = str(resources)
        locales = qt6 / "translations" / "qtwebengine_locales"
        if not locales.is_dir():
            locales = qt6 / "resources" / "locales"
        if locales.is_dir():
            os.environ["QTWEBENGINE_LOCALES_PATH"] = str(locales)
        bin_dir = qt6 / "bin"
        if bin_dir.is_dir():
            os.environ["PATH"] = str(bin_dir) + os.pathsep + os.environ.get("PATH", "")
        plugins = qt6 / "plugins"
        if plugins.is_dir():
            from PyQt6.QtCore import QCoreApplication
            QCoreApplication.setLibraryPaths([str(plugins)])
        break

    # Qt also looks next to the main EXE for the helper process
    helper = exe_dir / "QtWebEngineProcess.exe"
    internal_helper = exe_dir / "_internal" / "PyQt6" / "Qt6" / "bin" / "QtWebEngineProcess.exe"
    if internal_helper.is_file() and not helper.is_file():
        try:
            import shutil
            shutil.copy2(internal_helper, helper)
        except OSError:
            pass
    if helper.is_file():
        os.environ["QTWEBENGINEPROCESS_PATH"] = str(helper)


def _log_startup(msg: str) -> None:
    try:
        log_path = Path.home() / ".lumen" / "startup.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as f:
            f.write(msg + "\n")
    except OSError:
        pass


def main() -> int:
    try:
        return _main_impl()
    except Exception as exc:
        import traceback
        _log_startup(f"FATAL: {exc}\n{traceback.format_exc()}")
        raise


def _main_impl() -> int:
    bootstrap_frozen()
    start_tracing()
    mark("startup", version=APP_VERSION)
    _log_startup("LUMEN starting…")
    vpn = LumenVPN()
    if not vpn.start():
        print("FATAL: VPN failed to start.", file=sys.stderr)
        return 1

    settings = load_json(SETTINGS_PATH, DEFAULT_SETTINGS)
    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = perf_chromium_flags(
        secure=settings.get("secure_mode", True)
    )
    os.environ["QTWEBENGINE_DISABLE_SANDBOX"] = "1"
    # WebEngine uses chromium --proxy-server; avoid double-proxying Qt network stack

    get_shields().load()

    WEB_CACHE_PATH.mkdir(parents=True, exist_ok=True)
    STORAGE_PATH.mkdir(parents=True, exist_ok=True)

    app = QApplication(sys.argv)
    app.setApplicationName("LUMEN Browser")
    app.setApplicationDisplayName("LUMEN Browser")
    app.setApplicationVersion(APP_VERSION)
    app.setWindowIcon(app_icon())
    app.setStyle("Fusion")

    profile = QWebEngineProfile("lumen", app)
    profile.setCachePath(str(WEB_CACHE_PATH))
    profile.setPersistentStoragePath(str(STORAGE_PATH))
    apply_browser_identity(profile)
    profile.setHttpCacheMaximumSize(80 * 1024 * 1024)
    profile.setUrlRequestInterceptor(LumenRequestInterceptor(profile))

    window = LumenBrowser(vpn, profile)
    window.show()
    window._start_voice()
    _log_startup("LUMEN window shown")

    timer = QTimer()
    timer.timeout.connect(window.update_stats)
    timer.start(15000)

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
