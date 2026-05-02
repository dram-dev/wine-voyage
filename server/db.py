import asyncio
import logging
from typing import Optional

import asyncpg

from server.config import settings

logger = logging.getLogger(__name__)

_pool: Optional[asyncpg.Pool] = None


async def init_pool(retries: int = 5, base_delay: float = 1.0) -> asyncpg.Pool:
    """Create the global asyncpg pool, retrying with exponential backoff."""
    global _pool
    if _pool is not None:
        return _pool

    last_exc: Optional[BaseException] = None
    for attempt in range(retries):
        try:
            _pool = await asyncpg.create_pool(
                dsn=settings.database_url,
                min_size=1,
                max_size=10,
                command_timeout=30,
            )
            logger.info("Postgres pool initialized")
            return _pool
        except Exception as exc:
            last_exc = exc
            delay = base_delay * (2 ** attempt)
            logger.warning("DB connection attempt %d failed: %s (retry in %.1fs)", attempt + 1, exc, delay)
            await asyncio.sleep(delay)

    assert last_exc is not None
    raise last_exc


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
        logger.info("Postgres pool closed")


def get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("Database pool is not initialized")
    return _pool
