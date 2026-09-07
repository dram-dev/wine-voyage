"""Pluggable providers for critic scores and market valuations.

Wine Spectator, Robert Parker / Wine Advocate, Vinous, Wine-Searcher, and
CellarTracker all sit behind paid or partner-only APIs, so this app ships with
no live provider wired up. What it ships instead is the seam: implement
`ScoreProvider` / `ValuationProvider`, register it below, and the score
comparison and valuation endpoints will start returning real data alongside —
and ranked above — the model's estimates.

Until a real provider is registered, `/api/wines/{id}/scores` and
`/api/wines/{id}/valuation` fall back to an AI estimate that is stored and
surfaced with `source_kind = 'ai_estimate'`. Everything downstream (search
sort, cellar valuation, the UI badges) keys off that column, so an estimate is
never presented as a published score.
"""
from __future__ import annotations

from typing import Protocol

# A wine as the providers see it: the row from `wines`, already serialized.
Wine = dict


class ScoreProvider(Protocol):
    """Returns rows shaped like the `wine_scores` table (minus wine_id/id)."""

    name: str
    source_kind: str  # 'critic' or 'community'

    async def fetch(self, wine: Wine) -> list[dict]: ...


class ValuationProvider(Protocol):
    """Returns a dict of low/mid/high/currency, or None if the wine is unpriced."""

    name: str
    source_kind: str  # 'market'

    async def fetch(self, wine: Wine) -> dict | None: ...


# Register live providers here. Example:
#
#   from server.providers.wine_searcher import WineSearcherValuations
#   VALUATION_PROVIDERS.append(WineSearcherValuations(api_key=settings.wine_searcher_key))
#
SCORE_PROVIDERS: list[ScoreProvider] = []
VALUATION_PROVIDERS: list[ValuationProvider] = []


def has_live_scores() -> bool:
    return bool(SCORE_PROVIDERS)


def has_live_valuations() -> bool:
    return bool(VALUATION_PROVIDERS)
