import asyncio, asyncpg, os

DB_URL = os.environ.get("DATABASE_URL", "postgresql+asyncpg://sanjabai:***@sanjabai_pg:5432/sanjabai")
DB_URL = DB_URL.replace("+asyncpg", "")

async def main():
    conn = await asyncpg.connect(DB_URL)
    
    # Show one existing row as template
    row = await conn.fetchrow("SELECT * FROM model_catalog WHERE id = 'mistral-large'")
    print("Template row (mistral-large):")
    for k, v in dict(row).items():
        print(f"  {k}: {repr(v)}")
    
    # Check what models are currently available
    rows = await conn.fetch("SELECT id, availability FROM model_catalog WHERE availability = 'available' ORDER BY id")
    print(f"\nCurrently available ({len(rows)}):")
    for r in rows:
        print(f"  {r['id']}")
    
    await conn.close()

asyncio.run(main())
