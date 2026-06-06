"""LUMEN Mind — conversational AI with browser control (ChatGPT, Ollama, or built-in)."""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass

from ui.command_sanitize import sanitize_command, voice_transcript, wants_spoken_answer
from ui.intent_engine import is_wake_only, resolve_intent, should_use_browser_intent
from ui.knowledge import answer_from_page, answer_question, summarize_extractive
from ui.llm_client import LLMConfig, cached_ollama_status, chat_completion, is_chat_ready
from ui.memory import MemoryStore
from ui.wake_words import is_tts_garbage, looks_like_command


@dataclass
class PageContext:
    url: str = ""
    title: str = ""
    selection: str = ""
    body_text: str = ""


@dataclass
class AssistantAction:
    kind: str
    payload: str = ""


@dataclass
class AssistantConfig:
    user_name: str = "Josh"
    ai_provider: str = "builtin"
    lumen_ai_url: str = ""
    lumen_client_token: str = ""
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    use_ollama: bool = False


class LumenAssistant:
    """Chat-first assistant — optional ChatGPT or Ollama for natural conversation."""

    def __init__(self):
        self._memory = MemoryStore()
        self._config = AssistantConfig(user_name=self._memory.user_name)
        self._ollama_model = "llama3.2"
        self._ollama_available = False
        self._ollama_checked_at = 0.0

    def configure(
        self,
        *,
        user_name: str | None = None,
        ai_provider: str | None = None,
        lumen_ai_url: str | None = None,
        lumen_client_token: str | None = None,
        openai_api_key: str | None = None,
        openai_model: str | None = None,
        use_ollama: bool | None = None,
    ) -> None:
        if user_name:
            self._config.user_name = user_name.strip() or "Josh"
            self._memory.set_user_name(self._config.user_name)
        if ai_provider is not None:
            self._config.ai_provider = (ai_provider or "builtin").strip().lower()
        if lumen_ai_url is not None:
            self._config.lumen_ai_url = lumen_ai_url.strip()
        if lumen_client_token is not None:
            self._config.lumen_client_token = lumen_client_token.strip()
        if openai_api_key is not None:
            self._config.openai_api_key = openai_api_key.strip()
        if openai_model is not None and openai_model.strip():
            self._config.openai_model = openai_model.strip()
        if use_ollama is not None:
            self._config.use_ollama = use_ollama

    def _llm_config(self) -> LLMConfig:
        return LLMConfig(
            provider=self._config.ai_provider,
            lumen_ai_url=self._config.lumen_ai_url,
            lumen_client_token=self._config.lumen_client_token,
            openai_api_key=self._config.openai_api_key,
            openai_model=self._config.openai_model,
            ollama_model=self._ollama_model,
            use_ollama=self._config.use_ollama,
        )

    @property
    def ai_provider(self) -> str:
        return self._config.ai_provider

    @property
    def ollama_model(self) -> str:
        return self._ollama_model

    def refresh_ollama(self) -> bool:
        ready, model = cached_ollama_status(self._llm_config())
        self._ollama_available = ready
        if model:
            self._ollama_model = model
        return ready

    def ollama_ready(self) -> bool:
        if self._config.ai_provider == "ollama" or self._config.use_ollama:
            return self.refresh_ollama()
        return False

    def knowledge_ready(self) -> bool:
        """Free knowledge path — always available, no API key or subscription."""
        return True

    def chat_ready(self) -> bool:
        return self.knowledge_ready() or is_chat_ready(self._llm_config())

    def chat_status(self) -> tuple[str, str]:
        ready, model = cached_ollama_status(self._llm_config())
        if ready:
            return "Local AI", model
        return "Free knowledge", "Wikipedia"

    def process(
        self,
        message: str,
        ctx: PageContext,
        *,
        user_name: str | None = None,
        prefer_chat: bool = False,
    ) -> tuple[str, AssistantAction | None]:
        msg = message.strip()
        if user_name:
            self.configure(user_name=user_name)

        msg = voice_transcript(msg)
        if not msg or is_wake_only(msg) or is_tts_garbage(msg):
            return ("At your service.", None)

        use_browser = should_use_browser_intent(msg, ctx.url, ctx.title)
        if use_browser and not (prefer_chat and wants_spoken_answer(msg)):
            intent = resolve_intent(msg, ctx.url, ctx.title)
            if intent:
                action = AssistantAction(intent.kind, intent.payload)
                self._memory.add_turn(msg, intent.reply)
                return intent.reply, action

        reply, action = self._free_knowledge_answer(msg, ctx)
        self._memory.add_turn(msg, reply)
        return reply, action

    def _should_answer(self, msg: str, ctx: PageContext) -> bool:
        if wants_spoken_answer(msg):
            return True
        lower = msg.lower()
        if "?" in msg:
            return True
        if self._looks_conversational(lower):
            return True
        if re.search(r"\bsummarize\b", lower):
            return True
        if ctx.body_text and re.search(
            r"\b(this page|this site|this article|what does it say)\b", lower
        ):
            return True
        return False

    def _looks_conversational(self, lower: str) -> bool:
        starters = (
            "why ", "how ", "what ", "who ", "when ", "where ", "which ",
            "explain ", "tell me ", "describe ", "define ", "help me ",
            "can you ", "could you ", "give me ", "i want to know",
            "what's ", "whats ", "who's ", "how's ", "hows ",
            "hello", "hi ", "hey ", "thanks", "thank you", "chat ",
            "talk ", "write ", "create ", "imagine ", "suggest ",
        )
        return any(lower.startswith(s) for s in starters)

    def _free_knowledge_answer(self, msg: str, ctx: PageContext) -> tuple[str, AssistantAction | None]:
        """Free unlimited knowledge — local Ollama if installed, else Wikipedia & the web."""
        lower = msg.lower()
        if re.search(r"\bsummarize\b", lower):
            return ("Summarizing this page for you.", AssistantAction("summarize"))

        page_answer = answer_from_page(ctx.body_text, msg) if ctx.body_text else None
        if page_answer:
            return (page_answer, None)

        local = self._try_local_llm(msg, ctx)
        if local:
            return (local, None)

        if is_chat_ready(self._llm_config()) and self._config.ai_provider in ("lumen", "openai"):
            try:
                reply, action = self._chat_answer(msg, ctx)
                return (reply, action)
            except Exception:
                pass

        return self._answer(msg, ctx)

    def _try_local_llm(self, msg: str, ctx: PageContext) -> str | None:
        ready, _model = cached_ollama_status(self._llm_config())
        if not ready:
            return None
        try:
            cfg = LLMConfig(provider="ollama", ollama_model=self._ollama_model)
            return chat_completion(
                self._chat_messages(msg, ctx),
                cfg,
                temperature=0.7,
                max_tokens=700,
                timeout=45.0,
            )[:3000]
        except Exception:
            return None

    def _answer(self, msg: str, ctx: PageContext) -> tuple[str, AssistantAction | None]:
        lower = msg.lower()
        if re.search(r"\bsummarize\b", lower):
            return ("Summarizing this page for you.", AssistantAction("summarize"))

        page_answer = answer_from_page(ctx.body_text, msg) if ctx.body_text else None
        if page_answer:
            return (page_answer, None)

        history = self._memory.history_block()
        reply, wiki_url = answer_question(msg, history=history)
        if wiki_url and reply.endswith("web search."):
            return (reply, None)
        return (reply, None)

    def _system_prompt(self, ctx: PageContext) -> str:
        name = self._config.user_name
        prefs = self._memory.preferences_block()
        facts = self._memory.facts_block()
        page = ""
        if ctx.title and not ctx.url.startswith("lumen://"):
            page = f"Current page: {ctx.title}\n"
            if ctx.body_text:
                page += f"Page excerpt: {ctx.body_text[:1200]}\n"
        provider = self.chat_status()[0]
        return (
            f"You are LUMEN Mind — {name}'s voice assistant in their browser "
            f"({provider}). Be helpful, clear, and natural.\n"
            f"{facts}\n{prefs}\n{page}"
        ).strip()

    def _chat_messages(self, msg: str, ctx: PageContext) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = [
            {"role": "system", "content": self._system_prompt(ctx)},
        ]
        try:
            from ui.conversation_session import get_session
            live = get_session().context_hint()
            if live:
                messages.append({
                    "role": "system",
                    "content": f"Recent voice session:\n{live}",
                })
        except ImportError:
            pass
        messages.extend(self._memory.recent_chat_messages(40))
        messages.append({"role": "user", "content": msg})
        return messages

    def _chat_answer(self, msg: str, ctx: PageContext) -> tuple[str, AssistantAction | None]:
        lower = msg.lower()
        if re.search(r"\bsummarize\b", lower) and ctx.body_text:
            return ("Summarizing this page for you.", AssistantAction("summarize"))

        page_answer = answer_from_page(ctx.body_text, msg) if ctx.body_text else None
        if page_answer:
            return (page_answer, None)

        try:
            reply = chat_completion(
                self._chat_messages(msg, ctx),
                self._llm_config(),
                temperature=0.75,
                max_tokens=900,
                timeout=75.0,
            )
            if re.search(r"\bsummarize\b", lower):
                return ("Summarizing this page for you.", AssistantAction("summarize"))
            return reply[:4000], None
        except Exception:
            reply, wiki_url = answer_question(msg)
            if wiki_url and reply.endswith("web search."):
                return (reply, AssistantAction("navigate", wiki_url))
            return (reply, None)

    def summarize_text(self, text: str) -> str:
        text = text.strip()[:6000]
        if not text:
            return "No readable content on this page."
        if is_chat_ready(self._llm_config()):
            try:
                reply = chat_completion(
                    [
                        {
                            "role": "system",
                            "content": "Summarize in 4-6 bullet points. Be factual and concise.",
                        },
                        {"role": "user", "content": text},
                    ],
                    self._llm_config(),
                    temperature=0.4,
                    max_tokens=500,
                    timeout=60.0,
                )
                if reply:
                    return reply[:3000]
            except Exception:
                pass
        return summarize_extractive(text)
