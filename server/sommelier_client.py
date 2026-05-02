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


async def call_sommelier(prompt: str, max_tokens: int = 2048) -> dict[str, Any]:
    """Call Claude with the sommelier system prompt and parse JSON. Returns
    {"error": "..."} on any failure rather than raising."""
    try:
        client = get_anthropic()
        message = await client.messages.create(
            model=SOMMELIER_MODEL,
            max_tokens=max_tokens,
            system=SOMMELIER_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
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
