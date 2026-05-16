import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from server.db import close_pool, init_pool
from server.routes import (
    appellations,
    journal,
    sommelier,
    taste,
    top_rated,
    trips,
    wineries,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_pool()
    yield
    await close_pool()


app = FastAPI(title="Wine Voyage API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(appellations.router, prefix="/api")
app.include_router(journal.router, prefix="/api")
app.include_router(trips.router, prefix="/api")
app.include_router(taste.router, prefix="/api")
app.include_router(sommelier.router, prefix="/api")
app.include_router(wineries.router, prefix="/api")
app.include_router(top_rated.router, prefix="/api")
