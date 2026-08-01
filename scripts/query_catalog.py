import asyncio, os, json
os.environ.pop("HTTP_PROXY", None); os.environ.pop("HTTPS_PROXY", None)
os.environ.pop("http_proxy", None); os.environ.pop("https_proxy", None)
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

URL = os.environ.get("DATABASE_URL") or "postgresql+asyncpg://sanjhubai:sanjhubai@sanjhubai_pg:5432/sanjhubai"

async def main():
    eng = create_async_engine(URL)
    async with eng.connect() as c:
        r = await c.execute(text(
            "SELECT id, provider_model_id, display_name, provider, availability, "
            "input_per_million, output_per_million, currency, usd_input_per_million, usd_output_per_million "
            "FROM model_catalog ORDER BY provider, id"))
        rows = r.fetchall()
        print("COUNT:", len(rows))
        for row in rows:
            print(dict(zip(row._fields, row)))
    await eng.dispose()

asyncio.run(main())
