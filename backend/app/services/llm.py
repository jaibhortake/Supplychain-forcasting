"""Minimal client for a local Ollama server (https://ollama.com)."""

import httpx

from app.config import get_settings


class LLMUnavailableError(RuntimeError):
    pass


def is_available() -> bool:
    settings = get_settings()
    try:
        r = httpx.get(f"{settings.ollama_url}/api/tags", timeout=1.5)
        return r.status_code == 200
    except httpx.HTTPError:
        return False


def chat(messages: list[dict], temperature: float = 0.2) -> str:
    settings = get_settings()
    payload = {
        "model": settings.ollama_model,
        "messages": messages,
        "stream": False,
        "options": {"temperature": temperature, "num_ctx": settings.ollama_num_ctx},
    }
    try:
        r = httpx.post(f"{settings.ollama_url}/api/chat", json=payload, timeout=settings.ollama_timeout_seconds)
    except httpx.HTTPError as exc:
        raise LLMUnavailableError(
            f"Cannot reach Ollama at {settings.ollama_url}. Start it with `ollama serve` "
            f"and pull the model with `ollama pull {settings.ollama_model}`."
        ) from exc
    if r.status_code == 404:
        raise LLMUnavailableError(
            f"Model '{settings.ollama_model}' not found. Run `ollama pull {settings.ollama_model}`."
        )
    if r.status_code != 200:
        raise LLMUnavailableError(f"Ollama returned HTTP {r.status_code}: {r.text[:200]}")
    return r.json()["message"]["content"].strip()
