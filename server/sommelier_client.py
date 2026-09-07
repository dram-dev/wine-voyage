"""Shared helpers for calling Claude and caching responses."""
from __future__ import annotations

import json
import logging
from typing import Any, Optional

import asyncpg
from anthropic import AsyncAnthropic

from server.config import settings

logger = logging.getLogger(__name__)

SOMMELIER_SYSTEM_PROMPT = (
    "You are an expert sommelier writing for a wine guidebook. "
    "Respond ONLY with valid JSON matching the user's requested structure. "
    "No markdown, no preamble, no caveats."
)

LABEL_SYSTEM_PROMPT = (
    "You read wine bottle labels from photographs. Report only what you can "
    "actually see or confidently infer from the label; use null for anything "
    "you cannot read. Never invent a vintage or producer. "
    "Respond ONLY with valid JSON matching the user's requested structure. "
    "No markdown, no preamble, no caveats."
)

# Default model for AI calls. Update if Anthropic releases a newer Sonnet.
SOMMELIER_MODEL = "claude-sonnet-4-5-20250929"

_client: Optional[AsyncAnthropic] = None


def get_anthropic() -> AsyncAnthropic:
    global _client
    if _client is None:
        _client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    return _client


async def cache_get(pool: asyncpg.Pool, key: str) -> Optional[dict[str, Any]]:
    row = await pool.fetchrow(
        "SELECT response FROM ai_cache WHERE cache_key = $1 AND expires_at > NOW()",
        key,
    )
    if row is None:
        return None
    raw = row["response"]
    return raw if isinstance(raw, dict) else json.loads(raw)


async def cache_set(pool: asyncpg.Pool, key: str, response: dict[str, Any]) -> None:
    await pool.execute(
        """
        INSERT INTO ai_cache (cache_key, response)
        VALUES ($1, $2::jsonb)
        ON CONFLICT (cache_key) DO UPDATE
          SET response = EXCLUDED.response,
              created_at = NOW(),
              expires_at = NOW() + INTERVAL '30 days'
        """,
        key,
        json.dumps(response),
    )


def _strip_json(text: str) -> str:
    """Pull JSON out of a model response that might be wrapped in markdown fences."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[: -3]
        if text.startswith("json"):
            text = text[4:]
    return text.strip()


async def _call_claude(
    content: list[dict[str, Any]], system: str, max_tokens: int
) -> dict[str, Any]:
    """Send content blocks to Claude and parse the JSON reply. Returns
    {"error": "..."} on any failure rather than raising."""
    try:
        client = get_anthropic()
        message = await client.messages.create(
            model=SOMMELIER_MODEL,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": content}],
        )
        text = "".join(b.text for b in message.content if getattr(b, "type", None) == "text")
        try:
            return json.loads(_strip_json(text))
        except json.JSONDecodeError as exc:
            logger.warning("Sommelier returned non-JSON: %s", exc)
            return {"error": "invalid_json", "raw": text}
    except Exception as exc:
        logger.exception("Sommelier API call failed")
        return {"error": str(exc)}


async def call_sommelier(
    prompt: str, max_tokens: int = 2048, system: str = SOMMELIER_SYSTEM_PROMPT
) -> dict[str, Any]:
    return await _call_claude([{"type": "text", "text": prompt}], system, max_tokens)


async def call_sommelier_vision(
    prompt: str,
    images: list[tuple[str, str]],
    max_tokens: int = 2048,
    system: str = LABEL_SYSTEM_PROMPT,
) -> dict[str, Any]:
    """Same contract as call_sommelier, with images attached.

    `images` is a list of (media_type, base64_data) pairs — the image blocks go
    first so the model reads the label before the instructions, which is what
    Anthropic recommends for image-led prompts.
    """
    content: list[dict[str, Any]] = [
        {
            "type": "image",
            "source": {"type": "base64", "media_type": media_type, "data": data},
        }
        for media_type, data in images
    ]
    content.append({"type": "text", "text": prompt})
    return await _call_claude(content, system, max_tokens)
