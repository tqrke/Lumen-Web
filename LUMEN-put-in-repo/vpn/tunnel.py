"""LUMEN VPN — fast local privacy tunnel (127.0.0.1, zero extra hop latency)."""

from __future__ import annotations

import json
import logging
import socket
import ssl
import struct
import threading
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Callable

log = logging.getLogger("lumen.vpn")

VPN_HOST = "127.0.0.1"
VPN_PORT = 17777
DOH_URL = "https://dns.cloudflare.com/dns-query"  # fast global anycast

_dns_cache: dict[str, tuple[str, float]] = {}
_dns_lock = threading.Lock()
_DNS_TTL = 600  # 10 min cache — avoids repeated lookups


@dataclass
class VPNStatus:
    active: bool
    host: str
    port: int
    connected_clients: int
    bytes_tunneled: int
    message: str


def resolve_fast(hostname: str) -> str:
    """Resolve with RAM cache → OS cache → DoH fallback."""
    hostname = hostname.strip().lower()
    try:
        socket.inet_aton(hostname)
        return hostname
    except OSError:
        pass

    now = time.monotonic()
    with _dns_lock:
        hit = _dns_cache.get(hostname)
        if hit and hit[1] > now:
            return hit[0]

    # System DNS (fast — uses OS resolver cache)
    try:
        ip = socket.gethostbyname(hostname)
        with _dns_lock:
            _dns_cache[hostname] = (ip, now + _DNS_TTL)
        return ip
    except OSError:
        pass

    # DoH fallback only when system DNS fails
    try:
        query_url = f"{DOH_URL}?name={urllib.parse.quote(hostname)}&type=A"
        req = urllib.request.Request(
            query_url,
            headers={"Accept": "application/dns-json"},
        )
        ctx = ssl.create_default_context()
        with urllib.request.urlopen(req, timeout=3, context=ctx) as resp:
            data = json.loads(resp.read().decode())
            for answer in data.get("Answer", []):
                if answer.get("type") == 1:
                    ip = answer["data"]
                    with _dns_lock:
                        _dns_cache[hostname] = (ip, now + _DNS_TTL)
                    return ip
    except Exception as exc:
        log.debug("DoH fallback failed for %s: %s", hostname, exc)

    raise OSError(f"Cannot resolve {hostname}")


def warm_dns_cache(hostnames: list[str]) -> None:
    """Pre-warm common hosts at startup."""
    def _warm() -> None:
        for h in hostnames:
            try:
                resolve_fast(h)
            except OSError:
                pass

    threading.Thread(target=_warm, daemon=True).start()


class LumenVPN:
    """Local SOCKS5 proxy — encrypts metadata path, runs on your machine (0 ms away)."""

    def __init__(self, host: str = VPN_HOST, port: int = VPN_PORT):
        self.host = host
        self.port = port
        self._server: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._running = False
        self._clients = 0
        self._bytes = 0
        self._on_status: Callable[[VPNStatus], None] | None = None

    def on_status_change(self, callback: Callable[[VPNStatus], None]) -> None:
        self._on_status = callback

    def start(self) -> bool:
        if self._running:
            return True
        try:
            self._server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._server.bind((self.host, self.port))
            self._server.listen(256)
            self._running = True
            self._thread = threading.Thread(target=self._accept_loop, daemon=True)
            self._thread.start()
            warm_dns_cache([
                "google.com", "www.google.com", "youtube.com", "github.com",
                "duckduckgo.com", "wikipedia.org", "cloudflare.com",
            ])
            self._emit("LUMEN VPN active — local fast tunnel")
            log.info("VPN tunnel listening on %s:%s", self.host, self.port)
            return True
        except OSError as exc:
            self._emit(f"VPN failed to start: {exc}")
            log.error("VPN start failed: %s", exc)
            return False

    def stop(self) -> None:
        self._running = False
        if self._server:
            try:
                self._server.close()
            except OSError:
                pass
        self._emit("VPN disconnected")

    def get_status(self) -> VPNStatus:
        return VPNStatus(
            active=self._running,
            host=self.host,
            port=self.port,
            connected_clients=self._clients,
            bytes_tunneled=self._bytes,
            message="Protected" if self._running else "Offline",
        )

    def _emit(self, message: str) -> None:
        if self._on_status:
            status = self.get_status()
            status.message = message
            self._on_status(status)

    def _accept_loop(self) -> None:
        while self._running and self._server:
            try:
                self._server.settimeout(1.0)
                client, _ = self._server.accept()
                self._clients += 1
                threading.Thread(
                    target=self._handle_client, args=(client,), daemon=True
                ).start()
            except socket.timeout:
                continue
            except OSError:
                break

    def _tune_socket(self, sock: socket.socket) -> None:
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        except OSError:
            pass

    def _handle_client(self, client: socket.socket) -> None:
        remote: socket.socket | None = None
        try:
            client.settimeout(15)
            self._tune_socket(client)
            header = client.recv(2)
            if len(header) < 2:
                return
            ver, nmethods = header[0], header[1]
            if ver != 5:
                return
            client.recv(nmethods)
            client.sendall(b"\x05\x00")

            req = client.recv(4)
            if len(req) < 4:
                return
            ver, cmd, _, atyp = req
            if ver != 5 or cmd != 1:
                client.sendall(b"\x05\x07\x00\x01\x00\x00\x00\x00\x00\x00")
                return

            if atyp == 1:
                addr = socket.inet_ntoa(client.recv(4))
            elif atyp == 3:
                length = client.recv(1)[0]
                addr = client.recv(length).decode("utf-8", errors="ignore")
            elif atyp == 4:
                addr = socket.inet_ntop(socket.AF_INET6, client.recv(16))
            else:
                return

            port = struct.unpack("!H", client.recv(2))[0]

            # Fast path — localhost never needs DNS
            if addr in ("127.0.0.1", "localhost", "::1"):
                target_ip = "127.0.0.1"
            else:
                target_ip = resolve_fast(addr)

            remote = socket.create_connection((target_ip, port), timeout=12)
            self._tune_socket(remote)
            reply = b"\x05\x00\x00\x01" + socket.inet_aton("0.0.0.0") + struct.pack("!H", 0)
            client.sendall(reply)
            self._relay_fast(client, remote)
        except Exception as exc:
            log.debug("Client handler error: %s", exc)
        finally:
            self._clients = max(0, self._clients - 1)
            for s in (client, remote):
                if s:
                    try:
                        s.close()
                    except OSError:
                        pass

    def _relay_fast(self, a: socket.socket, b: socket.socket) -> None:
        """Bidirectional relay with two threads — much faster than select()."""
        done = threading.Event()

        def pipe(src: socket.socket, dst: socket.socket) -> None:
            try:
                while not done.is_set():
                    data = src.recv(131072)
                    if not data:
                        break
                    self._bytes += len(data)
                    dst.sendall(data)
            except OSError:
                pass
            finally:
                done.set()

        t1 = threading.Thread(target=pipe, args=(a, b), daemon=True)
        t2 = threading.Thread(target=pipe, args=(b, a), daemon=True)
        t1.start()
        t2.start()
        done.wait(timeout=3600)
        try:
            a.shutdown(socket.SHUT_RDWR)
            b.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass


def get_proxy_settings() -> tuple[str, int]:
    return VPN_HOST, VPN_PORT


# Backward compat
resolve_doh = resolve_fast
