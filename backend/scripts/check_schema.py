import asyncio, asyncpg, os

DB_URL = os.environ.get("DATABASE_URL", "postgresql+asyncpg://multiai:***@multiai_pg:5432/multiai")
DB_URL = DB_URL.replace("+asyncpg", "")

async def main():
    conn = await asyncpg.connect(DB_URL)
    
    # Check schema
    rows = await conn.fetch("""
        SELECT column_name, data_type, is_nullable 
        FROM information_schema.columns 
        WHERE table_name = 'model_catalog' 
        ORDER BY ordinal_position
    """)
    print("model_catalog columns:")
    for r in rows:
        print(f"  {r['column_name']} ({r['data_type']}) nullable={r['is_nullable']}")
    
    await conn.close()

asyncio.run(main())
