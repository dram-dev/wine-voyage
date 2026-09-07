"""Bring a database up to date in one command.

    python -m scripts.bootstrap_db            # create, migrate, seed
    python -m scripts.bootstrap_db --check    # report only, change nothing

Reads DATABASE_URL from .env (or the environment). Works against a local
Postgres or a hosted one — Neon, Supabase, RDS — because everything goes
through asyncpg rather than shelling out to psql.

Safe to re-run. Every migration in sql/ is written with IF NOT EXISTS, and the
ones already applied are recorded in schema_migrations and skipped, so running
this after a `git pull` applies exactly what is new.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import asyncpg

from server.config import settings

ROOT = Path(__file__).resolve().parent.parent
SQL_DIR = ROOT / "sql"
APPELLATIONS = ROOT / "data" / "appellations.json"

LEDGER = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    filename    TEXT PRIMARY KEY,
    applied_at  TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""


def split_dsn(dsn: str) -> tuple[str, str]:
    """Return (dsn pointing at the maintenance database, target database name)."""
    parts = urlsplit(dsn)
    name = parts.path.lstrip("/") or "postgres"
    admin = urlunsplit((parts.scheme, parts.netloc, "/postgres", parts.query, parts.fragment))
    return admin, name


async def ensure_database(dsn: str) -> bool:
    """Create the target database if it is missing. Returns True if we made it."""
    admin_dsn, name = split_dsn(dsn)
    try:
        conn = await asyncpg.connect(admin_dsn)
    except Exception as exc:
        # Hosted Postgres often blocks the maintenance database. That is fine:
        # the database itself is created through the provider's console, and the
        # connection check below will say so plainly if it does not exist.
        print(f"  · cannot reach the maintenance database ({exc.__class__.__name__}); assuming {name} already exists")
        return False
    try:
        exists = await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", name)
        if exists:
            return False
        await conn.execute(f'CREATE DATABASE "{name}"')
        print(f"  · created database {name}")
        return True
    finally:
        await conn.close()


async def apply_migrations(conn: asyncpg.Connection, check_only: bool) -> list[str]:
    if not check_only:
        await conn.execute(LEDGER)
    done: set[str] = set()
    if await conn.fetchval("SELECT to_regclass('schema_migrations')"):
        done = {r["filename"] for r in await conn.fetch("SELECT filename FROM schema_migrations")}

    pending = [p for p in sorted(SQL_DIR.glob("*.sql")) if p.name not in done]
    if check_only:
        return [p.name for p in pending]

    for path in pending:
        async with conn.transaction():
            await conn.execute(path.read_text())
            await conn.execute(
                "INSERT INTO schema_migrations (filename) VALUES ($1) ON CONFLICT DO NOTHING", path.name
            )
        print(f"  · applied {path.name}")
    return [p.name for p in pending]


async def seed_appellations() -> None:
    if not APPELLATIONS.exists():
        print("  · no data/appellations.json; skipping")
        return
    from scripts.seed_appellations import seed
    await seed()


async def summarize(conn: asyncpg.Connection) -> None:
    tables = await conn.fetchval(
        "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public'"
    )
    counts = {}
    for table in ("appellations", "cellars", "wines", "cellar_bottles"):
        if await conn.fetchval("SELECT to_regclass($1)", table):
            counts[table] = await conn.fetchval(f"SELECT count(*) FROM {table}")
    print(f"\n  {tables} tables")
    for table, n in counts.items():
        print(f"  {n:>7} {table}")


async def run(check_only: bool) -> int:
    dsn = settings.database_url
    shown = dsn.split("@")[-1]  # never print credentials
    print(f"Database: …@{shown}")

    if not check_only:
        await ensure_database(dsn)

    try:
        conn = await asyncpg.connect(dsn)
    except asyncpg.InvalidCatalogNameError:
        if check_only:
            print("\n✗ That database does not exist yet. Run without --check to create it.")
        else:
            print("\n✗ That database does not exist and could not be created.")
            print("  Create it in your provider's console, or run: createdb winevoyage")
        return 1
    except Exception as exc:
        print(f"\n✗ Could not connect: {exc}")
        print("  Check DATABASE_URL in .env, and that Postgres is running.")
        return 1

    try:
        pending = await apply_migrations(conn, check_only)
        if check_only:
            print(f"  {len(pending)} migration(s) pending" if pending else "  migrations up to date")
            for name in pending:
                print(f"  · {name}")
        elif not pending:
            print("  · migrations already up to date")

        if not check_only:
            await seed_appellations()
        await summarize(conn)
    finally:
        await conn.close()

    if not settings.anthropic_api_key:
        print("\n  ! ANTHROPIC_API_KEY is not set — label scanning and AI valuation will fail.")
        print("    Everything else, including autofill from the offline reference, works without it.")

    if not check_only:
        print("\n✓ Ready. Start the server with ./run.sh")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="report status without changing anything")
    args = parser.parse_args()
    sys.exit(asyncio.run(run(args.check)))


if __name__ == "__main__":
    main()
