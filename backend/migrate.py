"""Idempotent SQL migration runner for Sanjabai backend."""
from __future__ import annotations
import asyncio
from pathlib import Path
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncEngine


def split_sql(sql: str) -> list[str]:
    statements, buf = [], []
    quote = None
    line_comment = False
    block_comment = False
    i = 0
    while i < len(sql):
        ch = sql[i]
        nxt = sql[i + 1] if i + 1 < len(sql) else ""
        if line_comment:
            buf.append(ch)
            if ch == "\n":
                line_comment = False
            i += 1
            continue
        if block_comment:
            buf.append(ch)
            if ch == "*" and nxt == "/":
                buf.extend([nxt])
                i += 2
                block_comment = False
            else:
                i += 1
            continue
        if quote:
            buf.append(ch)
            if ch == quote:
                if nxt == quote:
                    buf.append(nxt)
                    i += 2
                    continue
                quote = None
            i += 1
            continue
        if ch == "-" and nxt == "-":
            buf.extend([ch, nxt])
            i += 2
            line_comment = True
            continue
        if ch == "/" and nxt == "*":
            buf.extend([ch, nxt])
            i += 2
            block_comment = True
            continue
        if ch in ("'", '"'):
            quote = ch
            buf.append(ch)
            i += 1
            continue
        if ch == ";":
            statement = "".join(buf).strip()
            if statement:
                statements.append(statement)
            buf = []
        else:
            buf.append(ch)
        i += 1
    statement = "".join(buf).strip()
    if statement:
        statements.append(statement)
    return statements


MIGRATIONS_DIR = Path(__file__).parent / "migrations"


async def migrate(engine: AsyncEngine, apply: bool = True) -> list[str]:
    """Apply pending SQL migrations in filename order.

    Returns the list of versions that were pending on entry.

    With apply=False nothing is executed and no schema_migrations row is
    written -- the function only reports. Container startup uses that mode so
    that a rebuild can never change the live schema on its own: `docker build`
    bakes in untracked files, so auto-applying on boot let unreviewed DDL reach
    production with no human decision in between.
    """
    async with engine.begin() as conn:
        await conn.execute(text(
            "CREATE TABLE IF NOT EXISTS schema_migrations "
            "(version TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())"
        ))
        result = await conn.execute(text("SELECT version FROM schema_migrations"))
        all_rows = result.all()
        applied = {row[0] for row in all_rows}

        pending = [p.name for p in sorted(MIGRATIONS_DIR.glob("*.sql"))
                   if p.name not in applied]
        if not apply:
            return pending

        for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
            version = path.name
            if version in applied:
                continue
            for statement in split_sql(path.read_text()):
                await conn.execute(text(statement))
            await conn.execute(
                text("INSERT INTO schema_migrations(version) VALUES (:version)"),
                {"version": version}
            )
        return pending


async def main() -> None:
    import os
    engine = create_async_engine(
        os.getenv("DATABASE_URL", "postgresql+asyncpg://sanjabai:sanjabai@127.0.0.1:5432/sanjabai"),
        echo=False
    )
    await migrate(engine)
    await engine.dispose()
    print("migrations done")


if __name__ == "__main__":
    asyncio.run(main())
