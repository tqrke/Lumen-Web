"""Global request interceptor — blocks ads/trackers on every resource."""

from PyQt6.QtWebEngineCore import QWebEngineUrlRequestInfo, QWebEngineUrlRequestInterceptor

from core.browser_identity import apply_request_headers
from shields.engine import get_shields


class LumenRequestInterceptor(QWebEngineUrlRequestInterceptor):
    def interceptRequest(self, info: QWebEngineUrlRequestInfo) -> None:
        url = info.requestUrl().toString()
        if url.startswith("lumen://") or url.startswith("data:"):
            return
        apply_request_headers(info)
        shields = get_shields()
        if shields.is_bot_protection_url(url):
            return
        if shields.is_ad_url(url):
            info.block(True)
            shields.record_ad_block()
