"""Hosted LUMEN AI — set your public proxy URL here before publishing."""

from __future__ import annotations

import os

# Set this to your deployed proxy (Railway, Fly.io, etc.) before shipping the public build.
# Example: "https://lumen-ai.yourdomain.com/v1/chat"
PUBLISHED_LUMEN_AI_URL = ""

DEFAULT_MODEL = "gpt-4o-mini"
APP_CLIENT_ID = "lumen-browser"


def resolve_lumen_ai_url(settings_url: str = "") -> str:
    """Endpoint the browser calls — no OpenAI key on the client."""
    if settings_url.strip():
        return settings_url.strip().rstrip("/")
    env = os.environ.get("LUMEN_AI_URL", "").strip()
    if env:
        return env.rstrip("/")
    if PUBLISHED_LUMEN_AI_URL.strip():
        return PUBLISHED_LUMEN_AI_URL.strip().rstrip("/")
    return "http://127.0.0.1:8787/v1/chat"
