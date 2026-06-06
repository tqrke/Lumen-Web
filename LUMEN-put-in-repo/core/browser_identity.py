"""Browser fingerprint — match embedded Chromium so retail CDNs (Tesco/Akamai) allow access."""

from __future__ import annotations

# Must match the Qt WebEngine Chromium major version (see defaultProfile().httpUserAgent()).
CHROME_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
)

MOBILE_SAFARI_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 "
    "Mobile/15E148 Safari/604.1"
)

# Optional Referer for retail retries (set/cleared by retail_loader).
_retail_referer: str | None = None


def set_retail_referer(url: str | None) -> None:
    global _retail_referer
    _retail_referer = url or None


def clear_retail_headers() -> None:
    set_retail_referer(None)


def apply_browser_identity(profile) -> None:
    """Desktop Chrome UA + light anti-automation script."""
    from PyQt6.QtWebEngineCore import QWebEngineScript

    profile.setHttpUserAgent(CHROME_USER_AGENT)

    script = QWebEngineScript()
    script.setName("lumen-anti-detect")
    script.setSourceCode(_ANTI_DETECT_JS)
    script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
    script.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
    script.setRunsOnSubFrames(True)
    for existing in profile.scripts().toList():
        if existing.name() == "lumen-anti-detect":
            profile.scripts().remove(existing)
            break
    profile.scripts().insert(script)


def apply_retail_user_agent(profile, *, mobile: bool = False) -> None:
    profile.setHttpUserAgent(MOBILE_SAFARI_UA if mobile else CHROME_USER_AGENT)


def apply_request_headers(info) -> None:
    """Only add Referer during retail retries — do not fake Sec-Fetch (triggers Akamai)."""
    from PyQt6.QtWebEngineCore import QWebEngineUrlRequestInfo

    if not _retail_referer:
        return
    if info.resourceType() != QWebEngineUrlRequestInfo.ResourceType.ResourceTypeMainFrame:
        return
    info.setHttpHeader(b"Referer", _retail_referer.encode("utf-8"))
    info.setHttpHeader(b"Accept-Language", b"en-GB,en;q=0.9")


# Hide automation flags some grocery/CDN sites check.
_ANTI_DETECT_JS = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
Object.defineProperty(navigator, 'languages', { get: () => ['en-GB', 'en'] });
if (!window.chrome) { window.chrome = { runtime: {} }; }
"""
