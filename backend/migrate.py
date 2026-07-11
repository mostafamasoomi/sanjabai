"""Idempotent SQL migration runner for Multiai backend."""
from __future__ import annotations

import asyncio
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncEngine

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


async def migrate(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version TEXT PRIMARY KEY,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """))
        applied = {
            row[0] for row in (await conn.execute(
                text("SELECT version FROM schema_migrations")
            )).all()
        }
        for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
            version = path.name
            if version in applied:
                continue
            sql = path.read_text()
            await conn.execute(text(sql))
            await conn.execute(
                text("INSERT INTO schema_migrations(version) VALUES (:version)"),
                {"version": version},
            )


async def main() -> None:
    import os
    engine = create_async_engine(
        os.getenv("DATABASE_URL", "postgresql+asyncpg://multiai:multiai@127.0.0.1:5432/multiai"),
        echo=False,
    )
    await migrate(engine)
    await engine.dispose()
    print("migrations done")


if __name__ == "__main__":
    asyncio.run(main())