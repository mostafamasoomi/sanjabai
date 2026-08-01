import asyncio, asyncpg, os

DB_URL = os.environ.get("DATABASE_URL", "postgresql+asyncpg://sanjhubai:***@sanjhubai_pg:5432/sanjhubai")
DB_URL = DB_URL.replace("+asyncpg", "")

async def main():
    conn = await asyncpg.connect(DB_URL)
    
    rows = await conn.fetch("""
        SELECT id, provider, availability, provenance 
        FROM model_catalog 
        WHERE availability = 'available' 
        ORDER BY provider, id
    """)
    print(f"Available models ({len(rows)}):")
    for r in rows:
        print(f"  {r['id']} | {r['provider']} | {r['provenance']}")
    
    await conn.close()

asyncio.run(main())
