"""Unified chat brain — hosted LUMEN AI (ChatGPT), direct OpenAI, or Ollama."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

from core.ai_config import APP_CLIENT_ID, DEFAULT_MODEL, resolve_lumen_ai_url


@dataclass
class LLMConfig:
    provider: str = "lumen"  # lumen | openai | ollama | builtin
    lumen_ai_url: str = ""
    lumen_client_token: str = ""
    openai_api_key: str = ""
    openai_model: str = DEFAULT_MODEL
    ollama_model: str = "llama3.2"
    use_ollama: bool = False


def is_chat_ready(cfg: LLMConfig) -> bool:
    if cfg.provider == "lumen":
        return bool(resolve_lumen_ai_url(cfg.lumen_ai_url))
    if cfg.provider == "openai":
        return bool(cfg.openai_api_key.strip())
    if cfg.provider == "ollama" or cfg.use_ollama:
        return check_ollama(cfg)[0]
    return False


def check_ollama(cfg: LLMConfig) -> tuple[bool, str]:
    try:
        req = urllib.request.Request(
            "http://127.0.0.1:11434/api/tags",
            headers={"User-Agent": "LUMEN"},
        )
        with urllib.request.urlopen(req, timeout=1.5) as resp:
            data = json.loads(resp.read())
            models = [m.get("name", "") for m in data.get("models", [])]
            if not models:
                return False, cfg.ollama_model
            for m in models:
                low = m.lower()
                if any(x in low for x in ("llama", "mistral", "phi", "gemma", "qwen", "deepseek")):
                    return True, m.split(":")[0]
            return True, models[0].split(":")[0]
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return False, cfg.ollama_model


def chat_completion(
    messages: list[dict[str, str]],
    cfg: LLMConfig,
    *,
    temperature: float = 0.7,
    max_tokens: int = 900,
    timeout: float = 60.0,
) -> str:
    provider = cfg.provider
    if provider == "builtin" and cfg.use_ollama:
        provider = "ollama"

    if provider == "lumen":
        return _lumen_hosted_chat(
            messages, cfg, temperature=temperature, max_tokens=max_tokens, timeout=timeout,
        )
    if provider == "openai":
        return _openai_chat(messages, cfg, temperature=temperature, max_tokens=max_tokens, timeout=timeout)
    if provider == "ollama":
        ready, model = check_ollama(cfg)
        if not ready:
            raise RuntimeError("Ollama is not running")
        cfg = LLMConfig(
            provider="ollama",
            ollama_model=model,
            openai_api_key=cfg.openai_api_key,
            openai_model=cfg.openai_model,
            use_ollama=cfg.use_ollama,
            lumen_ai_url=cfg.lumen_ai_url,
            lumen_client_token=cfg.lumen_client_token,
        )
        return _ollama_chat(messages, cfg, temperature=temperature, max_tokens=max_tokens, timeout=timeout)
    raise RuntimeError("No chat provider configured")


def _lumen_hosted_chat(
    messages: list[dict[str, str]],
    cfg: LLMConfig,
    *,
    temperature: float,
    max_tokens: int,
    timeout: float,
) -> str:
    base = resolve_lumen_ai_url(cfg.lumen_ai_url)
    url = base if base.endswith("/chat") else f"{base}/v1/chat"
    model = (cfg.openai_model or DEFAULT_MODEL).strip()
    body = json.dumps({
        "messages": messages,
        "model": model,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }).encode()
    headers = {
        "Content-Type": "application/json",
        "User-Agent": APP_CLIENT_ID,
        "X-Lumen-Client": APP_CLIENT_ID,
    }
    token = cfg.lumen_client_token.strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", errors="replace")[:240]
        except OSError:
            pass
        raise RuntimeError(f"LUMEN AI error ({exc.code}): {detail or exc.reason}") from exc
    reply = str(data.get("reply", "")).strip()
    if not reply:
        raise RuntimeError("LUMEN AI returned an empty reply")
    return reply


def _openai_chat(
    messages: list[dict[str, str]],
    cfg: LLMConfig,
    *,
    temperature: float,
    max_tokens: int,
    timeout: float,
) -> str:
    key = cfg.openai_api_key.strip()
    if not key:
        raise RuntimeError("OpenAI API key missing")
    model = (cfg.openai_model or DEFAULT_MODEL).strip()
    body = json.dumps({
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }).encode()
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
            "User-Agent": "LUMEN-Browser",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", errors="replace")[:240]
        except OSError:
            pass
        raise RuntimeError(f"OpenAI error ({exc.code}): {detail or exc.reason}") from exc
    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError("OpenAI returned no reply")
    reply = str(choices[0].get("message", {}).get("content", "")).strip()
    if not reply:
        raise RuntimeError("OpenAI returned an empty reply")
    return reply


def _ollama_chat(
    messages: list[dict[str, str]],
    cfg: LLMConfig,
    *,
    temperature: float,
    max_tokens: int,
    timeout: float,
) -> str:
    body = json.dumps({
        "model": cfg.ollama_model,
        "messages": messages,
        "stream": False,
        "options": {"temperature": temperature, "num_predict": max_tokens},
    }).encode()
    req = urllib.request.Request(
        "http://127.0.0.1:11434/api/chat",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read())
    reply = str(data.get("message", {}).get("content", "")).strip()
    if not reply:
        raise RuntimeError("Ollama returned an empty reply")
    return reply


_ollama_cache: tuple[float, tuple[bool, str]] = (0.0, (False, "llama3.2"))


def cached_ollama_status(cfg: LLMConfig) -> tuple[bool, str]:
    global _ollama_cache
    now = time.monotonic()
    if now - _ollama_cache[0] < 90:
        return _ollama_cache[1]
    status = check_ollama(cfg)
    _ollama_cache = (now, status)
    return status
