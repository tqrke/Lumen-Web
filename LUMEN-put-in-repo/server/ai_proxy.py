#!/usr/bin/env python3
"""LUMEN AI proxy — keeps your OpenAI key on the server, not in the published app.

Run locally:
  set OPENAI_API_KEY=sk-...
  python server/ai_proxy.py

Deploy to Railway/Fly/Render with env:
  OPENAI_API_KEY   (required)
  LUMEN_CLIENT_TOKEN (optional — clients must send Authorization: Bearer <token>)
  OPENAI_MODEL     (optional, default gpt-4o-mini)
  PORT             (optional, default 8787)
"""

from __future__ import annotations

import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

OPENAI_URL = "https://api.openai.com/v1/chat/completions"
DEFAULT_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini"
CLIENT_TOKEN = os.environ.get("LUMEN_CLIENT_TOKEN", "").strip()
API_KEY = os.environ.get("OPENAI_API_KEY", "").strip()
PORT = int(os.environ.get("PORT", "8787"))


def _json_response(handler: BaseHTTPRequestHandler, code: int, payload: dict) -> None:
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(code)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _read_json(handler: BaseHTTPRequestHandler) -> dict:
    length = int(handler.headers.get("Content-Length", "0") or 0)
    raw = handler.rfile.read(length) if length else b"{}"
    try:
        data = json.loads(raw.decode("utf-8"))
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def _authorized(handler: BaseHTTPRequestHandler) -> bool:
    if not CLIENT_TOKEN:
        return True
    auth = handler.headers.get("Authorization", "")
    return auth == f"Bearer {CLIENT_TOKEN}"


def _openai_chat(messages: list, *, model: str, temperature: float, max_tokens: int) -> str:
    if not API_KEY:
        raise RuntimeError("OPENAI_API_KEY not set on server")
    body = json.dumps({
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }).encode("utf-8")
    req = Request(
        OPENAI_URL,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {API_KEY}",
        },
        method="POST",
    )
    try:
        with urlopen(req, timeout=90) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:300]
        raise RuntimeError(f"OpenAI {exc.code}: {detail}") from exc
    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError("OpenAI returned no choices")
    reply = str(choices[0].get("message", {}).get("content", "")).strip()
    if not reply:
        raise RuntimeError("OpenAI returned empty content")
    return reply


class LumenAIHandler(BaseHTTPRequestHandler):
    server_version = "LUMEN-AI/1.0"

    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Lumen-Client")
        self.end_headers()

    def do_GET(self) -> None:
        if self.path.rstrip("/") in ("/v1/health", "/health"):
            _json_response(self, 200, {
                "ok": True,
                "model": DEFAULT_MODEL,
                "openai_configured": bool(API_KEY),
            })
            return
        _json_response(self, 404, {"error": "not found"})

    def do_POST(self) -> None:
        if self.path.rstrip("/") != "/v1/chat":
            _json_response(self, 404, {"error": "not found"})
            return
        if not _authorized(self):
            _json_response(self, 401, {"error": "unauthorized"})
            return
        data = _read_json(self)
        messages = data.get("messages")
        if not isinstance(messages, list) or not messages:
            _json_response(self, 400, {"error": "messages required"})
            return
        model = str(data.get("model") or DEFAULT_MODEL).strip() or DEFAULT_MODEL
        temperature = float(data.get("temperature", 0.7))
        max_tokens = int(data.get("max_tokens", 900))
        try:
            reply = _openai_chat(
                messages,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            _json_response(self, 200, {"reply": reply, "model": model})
        except Exception as exc:
            _json_response(self, 502, {"error": str(exc)[:400]})


def main() -> None:
    if not API_KEY:
        print("WARNING: OPENAI_API_KEY is not set — /v1/chat will fail.", file=sys.stderr)
    host = "0.0.0.0"
    httpd = ThreadingHTTPServer((host, PORT), LumenAIHandler)
    print(f"LUMEN AI proxy on http://{host}:{PORT}  (health: /v1/health)")
    httpd.serve_forever()


if __name__ == "__main__":
    main()
