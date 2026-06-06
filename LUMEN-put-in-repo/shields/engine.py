"""LUMEN Shields — global ad blocker + Guardio-style threat firewall."""

from __future__ import annotations

import re
import threading
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from core.paths import CACHE_PATH, FILTERS, user_data

# Curated high-impact ad/tracker domains (fast lookup, no lag)
BUILTIN_ADS = {
    "doubleclick.net", "googlesyndication.com", "googleadservices.com",
    "google-analytics.com", "googletagmanager.com", "googletagservices.com",
    "adservice.google.com", "pagead2.googlesyndication.com", "adnxs.com",
    "adsrvr.org", "adform.net", "advertising.com", "amazon-adsystem.com",
    "criteo.com", "criteo.net", "outbrain.com", "taboola.com", "moatads.com",
    "quantserve.com", "scorecardresearch.com", "hotjar.com", "mixpanel.com",
    "segment.io", "segment.com", "facebook.net", "connect.facebook.net",
    "analytics.twitter.com", "static.ads-twitter.com", "ads.linkedin.com",
    "snapads.com", "smartadserver.com", "pubmatic.com", "rubiconproject.com",
    "openx.net", "casalemedia.com", "3lift.com", "media.net", "yieldmo.com",
    "bidswitch.net", "contextweb.com", "lijit.com", "revcontent.com",
    "zergnet.com", "popads.net", "popcash.net", "propellerads.com",
    "mgid.com", "exoclick.com", "juicyads.com", "clickagy.com",
    "bounceexchange.com", "klaviyo.com", "omtrdc.net", "2mdn.net",
    "imrworldwide.com", "chartbeat.com", "newrelic.com", "nr-data.net",
    "bugsnag.com", "sentry.io", "intercom.io", "intercomcdn.com",
    "zdassets.com", "fontawesome.com", "disqus.com", "disquscdn.com",
    "addthis.com", "sharethis.com", "onesignal.com", "pushwoosh.com",
}

# Akamai / bot-manager hosts — never block or Tesco et al. fail their challenge scripts.
BOT_PROTECTION_SUFFIXES = (
    "akamai.net",
    "akamaized.net",
    "akamaihd.net",
    "edgekey.net",
    "edgesuite.net",
    "akstat.io",
)

BUILTIN_THREATS = {
    "malware-traffic-analysis.net", "urlhaus.abuse.ch", "testmalware.com",
    "phishing-test.com", "evil.com", "malware.com", "virus.net",
    "stealer-log.com", "credential-phish.net", "fake-login.com",
    "secure-update.fake", "wallet-drainer.io", "crypto-stealer.net",
}

# Patterns for suspicious URLs (Guardio-style heuristics)
SUSPICIOUS_PATTERNS = [
    re.compile(r"login.*\.(xyz|top|click|buzz|tk|ml|ga|cf|gq)$", re.I),
    re.compile(r"(verify|secure|update|account).*(paypal|amazon|microsoft|apple|google|bank)", re.I),
    re.compile(r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}.*login", re.I),
    re.compile(r"\.(zip|exe|scr|bat|cmd|ps1)$", re.I),
]


@dataclass
class ShieldStats:
    ads_blocked: int = 0
    trackers_blocked: int = 0
    threats_blocked: int = 0


@dataclass
class ShieldEngine:
    ad_domains: set[str] = field(default_factory=set)
    threat_domains: set[str] = field(default_factory=set)
    stats: ShieldStats = field(default_factory=ShieldStats)
    ad_block_enabled: bool = True
    firewall_enabled: bool = True
    block_level: str = "aggressive"  # standard | aggressive | paranoid
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def load(self) -> None:
        with self._lock:
            self.ad_domains = set(BUILTIN_ADS)
            self.threat_domains = set(BUILTIN_THREATS)
            self._load_file(FILTERS / "ads_domains.txt", self.ad_domains)
            self._load_file(FILTERS / "threats_domains.txt", self.threat_domains)
            cache_ads = CACHE_PATH / "ads_domains.cache"
            cache_threats = CACHE_PATH / "threats_domains.cache"
            if cache_ads.exists():
                self._load_file(cache_ads, self.ad_domains)
            if cache_threats.exists():
                self._load_file(cache_threats, self.threat_domains)
        threading.Thread(target=self._update_feeds_async, daemon=True).start()

    def _load_file(self, path: Path, target: set[str]) -> None:
        if not path.exists():
            return
        try:
            for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
                line = line.strip().lower()
                if line and not line.startswith("#") and not line.startswith("!"):
                    if line.startswith("||") and line.endswith("^"):
                        line = line[2:-1]
                    elif line.startswith("|"):
                        line = line[1:]
                    if "." in line and " " not in line:
                        target.add(line.removeprefix("www."))
        except OSError:
            pass

    def _update_feeds_async(self) -> None:
        try:
            CACHE_PATH.mkdir(parents=True, exist_ok=True)
            self._fetch_domains(
                "https://raw.githubusercontent.com/StevenBlack/hosts/master/hosts",
                CACHE_PATH / "ads_domains.cache",
                self.ad_domains,
            )
            self._fetch_domains(
                "https://openphish.com/feed.txt",
                CACHE_PATH / "threats_domains.cache",
                self.threat_domains,
                is_url_list=True,
            )
        except Exception:
            pass

    def _fetch_domains(
        self, url: str, cache: Path, target: set[str], is_url_list: bool = False
    ) -> None:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "LUMEN-Browser/2"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                text = resp.read().decode("utf-8", errors="ignore")
            cache.write_text(text, encoding="utf-8")
            new_domains: set[str] = set()
            for line in text.splitlines():
                line = line.strip().lower()
                if not line or line.startswith("#"):
                    continue
                if is_url_list:
                    if line.startswith("http"):
                        from urllib.parse import urlparse
                        host = urlparse(line).hostname
                        if host:
                            new_domains.add(host.removeprefix("www."))
                else:
                    parts = line.split()
                    if len(parts) >= 2 and parts[0] == "0.0.0.0":
                        d = parts[1].removeprefix("www.")
                        if "." in d and not d.startswith("0"):
                            new_domains.add(d)
            with self._lock:
                target.update(new_domains)
        except Exception:
            pass

    def is_bot_protection_url(self, url: str) -> bool:
        host = _extract_host(url)
        if not host:
            return False
        return any(host == s or host.endswith("." + s) for s in BOT_PROTECTION_SUFFIXES)

    def is_ad_url(self, url: str) -> bool:
        if not self.ad_block_enabled:
            return False
        if self.is_bot_protection_url(url):
            return False
        host = _extract_host(url)
        if not host:
            return False
        with self._lock:
            if host in self.ad_domains:
                return True
            # O(labels) suffix check instead of O(n) loop over all domains
            parts = host.split(".")
            for i in range(len(parts) - 1):
                suffix = ".".join(parts[i:])
                if suffix in self.ad_domains:
                    return True
        if self.block_level == "paranoid":
            lower = url.lower()
            return any(k in lower for k in ("/ads/", "/ad.", "banner", "popup"))
        return False

    def check_threat(self, url: str) -> tuple[bool, str]:
        """Returns (is_threat, reason)."""
        if not self.firewall_enabled:
            return False, ""
        host = _extract_host(url)
        if not host:
            return False, ""
        with self._lock:
            if host in self.threat_domains:
                return True, "Known malicious domain (LUMEN Firewall)"
            parts = host.split(".")
            for i in range(len(parts) - 1):
                suffix = ".".join(parts[i:])
                if suffix in self.threat_domains:
                    return True, "Known malicious domain (LUMEN Firewall)"
        for pat in SUSPICIOUS_PATTERNS:
            if pat.search(url):
                return True, "Suspicious URL pattern detected (LUMEN Guard)"
        if self.block_level == "paranoid" and host.count(".") >= 3:
            tld = host.rsplit(".", 1)[-1]
            if tld in {"xyz", "top", "click", "buzz", "tk", "ml", "ga", "cf", "gq", "pw"}:
                return True, "High-risk domain extension (LUMEN Guard)"
        return False, ""

    def record_ad_block(self) -> None:
        self.stats.ads_blocked += 1

    def record_threat_block(self) -> None:
        self.stats.threats_blocked += 1


def _extract_host(url: str) -> str:
    try:
        from urllib.parse import urlparse
        h = urlparse(url).hostname
        return h.lower().removeprefix("www.") if h else ""
    except Exception:
        return ""


# Singleton for app-wide use
_engine: ShieldEngine | None = None


def get_shields() -> ShieldEngine:
    global _engine
    if _engine is None:
        _engine = ShieldEngine()
        _engine.load()
    return _engine
