"""Ollama HTTP client with memory-safe keep_alive management.

All prompts pass through the sanitizer before being sent to the LLM.
This is the LAST line of defense against prompt injection from
internet-sourced content that may be embedded in context packs.
"""
from __future__ import annotations

import json
import re

import httpx

from app.pipeline.sanitizer import sanitize_for_llm
from app.settings import settings
from app.utils.logging import get_logger

log = get_logger("ollama")

_TIMEOUT = httpx.Timeout(connect=10.0, read=300.0, write=10.0, pool=30.0)


def _strip_think_tags(text: str) -> str:
    """Remove <think>...</think> blocks from deepseek-r1 responses."""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


def _extract_json(text: str) -> str:
    """Extract JSON from a response that may contain markdown fences."""
    # Try to find JSON in code fences
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    # Try to find raw JSON object
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        return match.group(0).strip()
    return text.strip()


async def chat(
    model: str,
    prompt: str,
    system: str | None = None,
    temperature: float = 0.3,
) -> str:
    """Send a chat request to Ollama and return the response text.

    Uses keep_alive=0 (or configured value) to unload the model
    immediately after the call, preserving RAM for the next model.
    """
    # ── Sanitize user prompt (contains internet-sourced data) ──
    prompt = sanitize_for_llm(prompt, context_label=f"ollama/{model}")

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {"temperature": temperature},
        "keep_alive": settings.ollama_keep_alive,
    }

    log.info("ollama.chat.request", model=model, prompt_len=len(prompt))

    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(
            f"{settings.ollama_base_url}/api/chat",
            json=payload,
        )
        resp.raise_for_status()

    data = resp.json()
    content = data.get("message", {}).get("content", "")
    content = _strip_think_tags(content)

    log.info("ollama.chat.response", model=model, response_len=len(content))
    return content


async def chat_json(
    model: str,
    prompt: str,
    system: str | None = None,
    temperature: float = 0.3,
) -> dict:
    """Chat with Ollama and parse the response as JSON."""
    raw = await chat(model, prompt, system=system, temperature=temperature)
    extracted = _extract_json(raw)

    try:
        return json.loads(extracted)
    except json.JSONDecodeError as exc:
        log.error("ollama.json_parse_error", model=model, raw=raw[:500], error=str(exc))
        raise ValueError(f"Failed to parse JSON from {model}: {exc}") from exc


async def health_check() -> dict:
    """Check Ollama connectivity and list available models."""
    async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
        resp = await client.get(f"{settings.ollama_base_url}/api/tags")
        resp.raise_for_status()
    return resp.json()
