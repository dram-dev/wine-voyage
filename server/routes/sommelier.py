from fastapi import APIRouter
from pydantic import BaseModel, Field

from server.db import get_pool
from server.sommelier_client import cache_get, cache_set, call_sommelier

router = APIRouter(tags=["sommelier"])


class SommelierRequest(BaseModel):
    cache_key: str = Field(min_length=1, max_length=512)
    prompt: str = Field(min_length=1)
    max_tokens: int = Field(default=2048, ge=128, le=8192)


@router.post("/sommelier")
async def sommelier(req: SommelierRequest) -> dict:
    pool = get_pool()
    cached = await cache_get(pool, req.cache_key)
    if cached is not None:
        return {"cached": True, "response": cached}

    response = await call_sommelier(req.prompt, max_tokens=req.max_tokens)
    if "error" not in response:
        await cache_set(pool, req.cache_key, response)
    return {"cached": False, "response": response}
