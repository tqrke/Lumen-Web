"""Control Microsoft Edge for grocery sites — avoids WebView2 crashes inside LUMEN."""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

log = logging.getLogger("lumen.edge")

EDGE_PROFILE = Path.home() / ".lumen" / "edge-grocery-profile"
DEBUG_PORT = 9223
_DEFAULT_GROCERY_URL = "https://www.tesco.com/groceries/en-GB/"
_EDGE_PROC: subprocess.Popen | None = None
_LOCK = threading.Lock()
_LAST_GROCERY_URL = _DEFAULT_GROCERY_URL
_WS_ORIGIN = f"http://127.0.0.1:{DEBUG_PORT}"


def _edge_log(msg: str) -> None:
    try:
        log_path = Path.home() / ".lumen" / "voice.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as f:
            f.write(f"{datetime.now():%H:%M:%S} EDGE: {msg}\n")
    except OSError:
        pass


def _edge_path() -> str | None:
    found = shutil.which("msedge")
    if found:
        return found
    for candidate in (
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ):
        if Path(candidate).is_file():
            return candidate
    return None


def _edge_launch_args(url: str) -> list[str]:
    return [
        _edge_path() or "msedge",
        f"--remote-debugging-port={DEBUG_PORT}",
        "--remote-allow-origins=*",
        f"--user-data-dir={EDGE_PROFILE}",
        "--no-first-run",
        "--new-window",
        url,
    ]


def _http_json(url: str, timeout: float = 2.0):
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", errors="ignore"))


def _cdp_ready(port: int = DEBUG_PORT, timeout: float = 12.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            _http_json(f"http://127.0.0.1:{port}/json/version", timeout=1.0)
            return True
        except (urllib.error.URLError, TimeoutError, OSError):
            time.sleep(0.15)
    return False


def _page_ws_url(port: int = DEBUG_PORT, *, prefer: str = "") -> str | None:
    try:
        tabs = _http_json(f"http://127.0.0.1:{port}/json", timeout=2.0)
    except (urllib.error.URLError, TimeoutError, OSError):
        return None
    if not isinstance(tabs, list):
        return None
    prefer_l = prefer.lower()
    best = None
    for tab in tabs:
        if tab.get("type") != "page":
            continue
        u = str(tab.get("url", "")).lower()
        if "devtools://" in u or u in ("about:blank", ""):
            continue
        ws = tab.get("webSocketDebuggerUrl")
        if not ws:
            continue
        if prefer_l and prefer_l in u:
            return ws
        if "tesco.com" in u or "sainsbury" in u or "asda.com" in u or "morrisons" in u:
            best = ws
    if best:
        return best
    for tab in tabs:
        if tab.get("type") == "page":
            u = str(tab.get("url", "")).lower()
            if "devtools://" not in u:
                return tab.get("webSocketDebuggerUrl")
    return None


def _ws_connect(ws_url: str, *, timeout: float = 15.0):
    import websocket  # websocket-client

    return websocket.create_connection(
        ws_url,
        timeout=timeout,
        header=[f"Origin: {_WS_ORIGIN}"],
    )


def _cdp_eval(ws_url: str, js: str, *, timeout: float = 25.0) -> str | None:
    try:
        import websocket  # noqa: F401
    except ImportError:
        _edge_log("websocket-client not installed")
        return None

    ws = None
    try:
        ws = _ws_connect(ws_url, timeout=timeout)
        msg_id = 0

        def send(method: str, params: dict | None = None) -> int:
            nonlocal msg_id
            msg_id += 1
            ws.send(json.dumps({"id": msg_id, "method": method, "params": params or {}}))
            return msg_id

        pending = {send("Runtime.enable"), send("Page.enable")}
        eval_id = send(
            "Runtime.evaluate",
            {
                "expression": js,
                "returnByValue": True,
                "awaitPromise": True,
                "userGesture": True,
            },
        )
        deadline = time.time() + timeout
        while time.time() < deadline:
            raw = ws.recv()
            data = json.loads(raw)
            rid = data.get("id")
            if rid in pending:
                pending.discard(rid)
            if rid == eval_id:
                if "error" in data:
                    _edge_log(f"CDP eval error: {data['error']}")
                    return None
                value = data.get("result", {}).get("result", {}).get("value")
                return str(value) if value is not None else ""
    except Exception as exc:
        _edge_log(f"CDP eval failed: {exc}")
        return None
    finally:
        if ws:
            try:
                ws.close()
            except Exception:
                pass
    return None


def _cdp_navigate(url: str) -> bool:
    ws = _page_ws_url()
    if not ws:
        return False
    ws_conn = None
    try:
        ws_conn = _ws_connect(ws, timeout=10)
        msg_id = 0

        def send(method: str, params: dict | None = None) -> int:
            nonlocal msg_id
            msg_id += 1
            ws_conn.send(json.dumps({"id": msg_id, "method": method, "params": params or {}}))
            return msg_id

        nav_id = send("Page.navigate", {"url": url})
        deadline = time.time() + 10
        while time.time() < deadline:
            data = json.loads(ws_conn.recv())
            if data.get("id") == nav_id:
                ok = "error" not in data
                _edge_log(f"CDP navigate {'ok' if ok else 'fail'}: {url[:80]}")
                return ok
    except Exception as exc:
        _edge_log(f"CDP navigate failed: {exc}")
        return False
    finally:
        if ws_conn:
            try:
                ws_conn.close()
            except Exception:
                pass
    return False


def _http_open_url(url: str) -> bool:
    """Open URL in Edge via CDP HTTP API (no WebSocket)."""
    try:
        # Encode the whole URL — search URLs contain ?query= which breaks /json/new? parsing.
        encoded = urllib.parse.quote(url, safe="")
        req = urllib.request.Request(
            f"http://127.0.0.1:{DEBUG_PORT}/json/new?{encoded}",
            method="PUT",
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            body = resp.read().decode("utf-8", errors="ignore")
            opened = ""
            try:
                opened = str(json.loads(body).get("url", ""))
            except json.JSONDecodeError:
                pass
            ok = resp.status == 200
            _edge_log(
                f"HTTP new tab {'ok' if ok else 'fail'}: {url[:80]}"
                + (f" -> opened {opened[:80]}" if opened else "")
            )
            return ok
    except Exception as exc:
        _edge_log(f"HTTP new tab failed: {exc}")
        return False


def _pids_on_port(port: int) -> list[int]:
    """Return PIDs listening on a TCP port (Windows netstat)."""
    try:
        out = subprocess.check_output(
            ["netstat", "-ano", "-p", "tcp"],
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="ignore",
        )
    except (subprocess.SubprocessError, OSError):
        return []
    pids: list[int] = []
    needle = f":{port}"
    for line in out.splitlines():
        if "LISTENING" not in line or needle not in line:
            continue
        parts = line.split()
        if len(parts) < 5:
            continue
        try:
            pids.append(int(parts[-1]))
        except ValueError:
            continue
    return pids


def _kill_edge_process() -> None:
    global _EDGE_PROC
    if _EDGE_PROC and _EDGE_PROC.poll() is None:
        try:
            _EDGE_PROC.terminate()
            _EDGE_PROC.wait(timeout=3)
        except Exception:
            try:
                _EDGE_PROC.kill()
            except Exception:
                pass
    _EDGE_PROC = None
    for pid in _pids_on_port(DEBUG_PORT):
        try:
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
                check=False,
            )
            _edge_log(f"killed pid={pid} on port {DEBUG_PORT}")
        except (subprocess.SubprocessError, OSError):
            pass
    time.sleep(0.35)


def open_grocery_in_edge(url: str, *, force: bool = False) -> str:
    """Open a grocery URL in Microsoft Edge (separate process with CDP)."""
    global _EDGE_PROC, _LAST_GROCERY_URL
    edge = _edge_path()
    if not edge:
        return "Edge not found"

    EDGE_PROFILE.mkdir(parents=True, exist_ok=True)
    url = url.strip()
    _LAST_GROCERY_URL = url

    with _LOCK:
        if not force and _cdp_ready(timeout=0.5):
            if _cdp_navigate(url):
                return "Edge"
            if _http_open_url(url):
                return "Edge"
            _edge_log("CDP up but navigate failed — relaunching Edge")

        _kill_edge_process()
        try:
            _EDGE_PROC = subprocess.Popen(
                _edge_launch_args(url),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            _edge_log(f"launched Edge pid={_EDGE_PROC.pid} url={url}")
        except OSError as exc:
            _edge_log(f"launch failed: {exc}")
            return "Edge (failed)"

    if _cdp_ready():
        return "Edge"
    return "Edge"


def ensure_grocery_edge(*, url: str | None = None, force: bool = False) -> bool:
    """Make sure Edge CDP can control the Tesco tab."""
    target = (url or _LAST_GROCERY_URL or _DEFAULT_GROCERY_URL).strip()
    if not force and _cdp_ready(timeout=0.4) and _page_ws_url(prefer="tesco"):
        # Verify WebSocket actually works (403 if missing --remote-allow-origins)
        ws = _page_ws_url(prefer="tesco")
        if ws:
            try:
                conn = _ws_connect(ws, timeout=3)
                conn.close()
                _edge_log("ensure: CDP ready")
                return True
            except Exception as exc:
                _edge_log(f"ensure: WS probe failed ({exc}) — relaunch")
    _edge_log(f"ensure: relaunch Edge for {target[:80]}")
    result = open_grocery_in_edge(target, force=True)
    ok = result != "Edge (failed)" and _cdp_ready(timeout=8.0)
    _edge_log(f"ensure: ok={ok}")
    return ok


def edge_navigate_grocery(url: str) -> bool:
    """Navigate the Tesco tab in Edge to url."""
    if ensure_grocery_edge():
        if _cdp_navigate(url):
            return True
        if _http_open_url(url):
            return True
    _edge_log(f"navigate fallback: launch Edge to {url[:80]}")
    return open_grocery_in_edge(url, force=True) != "Edge (failed)"


def edge_search_tesco(item: str) -> bool:
    """Search Tesco in Edge — uses direct search URL."""
    from ui.grocery_control import normalize_item, tesco_search_url

    item = normalize_item(item)
    url = tesco_search_url(item)
    _edge_log(f"search tesco: {item!r} -> {url}")
    return edge_navigate_grocery(url)


def edge_eval_page(js: str, *, prefer: str = "") -> str | None:
    """Run JS in the active Edge page tab (Tesco, etc.)."""
    if not _cdp_ready(timeout=0.6):
        _edge_log("eval page: no CDP")
        return None
    ws = _page_ws_url(prefer=prefer) if prefer else _page_ws_url()
    if not ws:
        ws = _page_ws_url(prefer="tesco")
    if not ws:
        _edge_log("eval page: no tab")
        return None
    result = _cdp_eval(ws, js)
    _edge_log(f"eval page: {(result or '')[:80]}")
    return result


def edge_eval_grocery(js: str, *, url_hint: str = "tesco") -> str | None:
    """Run JS in the Edge grocery tab (for add-to-basket automation)."""
    if not ensure_grocery_edge():
        _edge_log("eval: no CDP session")
        return None
    return edge_eval_page(js, prefer=url_hint)


def edge_is_active() -> bool:
    return _cdp_ready(timeout=0.3) and bool(_page_ws_url(prefer="tesco"))
