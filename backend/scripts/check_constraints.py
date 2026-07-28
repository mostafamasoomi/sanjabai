import asyncio, asyncpg, os

DB_URL = os.environ.get("DATABASE_URL", "postgresql+asyncpg://multiai:***@multiai_pg:5432/multiai")
DB_URL = DB_URL.replace("+asyncpg", "")

async def main():
    conn = await asyncpg.connect(DB_URL)
    
    rows = await conn.fetch("""
        SELECT conname, pg_get_constraintdef(oid) as def
        FROM pg_constraint 
        WHERE conrelid = 'model_catalog'::regclass
    """)
    print("Constraints:")
    for r in rows:
        print(f"  {r['conname']}: {r['def']}")
    
    await conn.close()

asyncio.run(main())
