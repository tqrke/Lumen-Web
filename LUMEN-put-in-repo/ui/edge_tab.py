"""Microsoft Edge WebView2 tab — real Edge engine, passes Tesco/Akamai bot checks."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QUrl, pyqtSignal

EDGE_USER_DATA = Path.home() / ".lumen" / "edge-webview2"

# WebView2 inside LUMEN crashes alongside Qt WebEngine — use core.edge_session instead.
EDGE_TAB_AVAILABLE = False
QtWebView2Widget = object  # type: ignore


class _EdgePage:
    """Minimal QWebEnginePage-like shim for grocery JS automation."""

    def __init__(self, tab: "EdgeTab") -> None:
        self._tab = tab

    def runJavaScript(self, js: str, callback=None) -> None:
        self._tab.run_javascript(js, callback)


class _EdgeHistory:
    def __init__(self, tab: "EdgeTab") -> None:
        self._tab = tab

    def canGoBack(self) -> bool:
        return self._tab.can_go_back()

    def canGoForward(self) -> bool:
        return self._tab.can_go_forward()


if EDGE_TAB_AVAILABLE:

    class EdgeTab(QtWebView2Widget):
        """Browser tab backed by system Edge — works on Tesco and other Akamai sites."""

        title_changed = pyqtSignal(str)
        url_changed = pyqtSignal(QUrl)

        def __init__(self, browser, parent=None):
            EDGE_USER_DATA.mkdir(parents=True, exist_ok=True)
            super().__init__(
                user_data_folder=str(EDGE_USER_DATA),
                lazyload=False,
                context_menus=True,
                parent=parent,
            )
            self._browser = browser
            self._hibernating = False
            self._last_active = 0.0
            self._saved_url = ""
            self._current_url = ""
            self._current_title = "Loading…"
            self._page = _EdgePage(self)
            self._history = _EdgeHistory(self)
            self._dev_page = None

            self.bridge.domContentLoaded.connect(self._on_dom_ready)
            self.bridge.initialization_done.connect(self._on_init)

        def _on_init(self, ok: bool, err: str) -> None:
            if not ok:
                self._current_title = "Edge failed to start"
                self.load_finished.emit(False)
                return
            core = self._webview.CoreWebView2
            core.SourceChanged += self._on_source_changed
            core.DocumentTitleChanged += self._on_title_changed

        def _on_source_changed(self, sender, args) -> None:
            try:
                u = str(sender.Source)
                if u and u != "about:blank":
                    self._current_url = u
                    self.url_changed.emit(QUrl(u))
            except Exception:
                pass

        def _on_title_changed(self, sender, args) -> None:
            try:
                self._current_title = str(sender.DocumentTitle or "")
                self.title_changed.emit(self._current_title)
            except Exception:
                pass

        def _on_dom_ready(self) -> None:
            self.load_finished.emit(True)

        def page(self) -> _EdgePage:
            return self._page

        def history(self) -> _EdgeHistory:
            return self._history

        def url(self) -> QUrl:
            return QUrl(self._current_url or "about:blank")

        def title(self) -> str:
            return self._current_title

        def load(self, qurl: QUrl) -> None:
            u = qurl.toString()
            self._current_url = u
            self._current_title = "Loading…"
            self.load_url(u)

        def back(self) -> None:
            if self.is_ready:
                self._webview.CoreWebView2.GoBack()

        def forward(self) -> None:
            if self.is_ready:
                self._webview.CoreWebView2.GoForward()

        def can_go_back(self) -> bool:
            if self.is_ready:
                return bool(self._webview.CoreWebView2.CanGoBack)
            return False

        def can_go_forward(self) -> bool:
            if self.is_ready:
                return bool(self._webview.CoreWebView2.CanGoForward)
            return False

        def run_javascript(self, js: str, callback=None) -> None:
            def _wrap(result: dict) -> None:
                if callback is None:
                    return
                if result.get("success"):
                    callback(result.get("result"))
                else:
                    callback(None)

            self.evaluate_js(js, _wrap if callback else None)

        load_finished = pyqtSignal(bool)

else:

    class EdgeTab:  # type: ignore
        pass
