import asyncio, asyncpg, os
from datetime import datetime, timezone

DB_URL = os.environ.get("DATABASE_URL", "postgresql+asyncpg://sanjabai:***@sanjabai_pg:5432/sanjabai")
DB_URL = DB_URL.replace("+asyncpg", "")

FREELM_MODELS = [
    "freellmapi-auto", "fusion", "gemini-3.5-flash", "gpt-oss-120b",
    "llama-3.3-70b", "gpt-oss-20b", "gpt-oss-safeguard-20b",
    "gemma-4-31b-it", "gemini-2.5-flash", "gemma-4-26b-it",
    "gemini-2.5-flash-lite", "llama-3.1-8b-instant",
    "gemini-3.1-flash-lite", "compound", "compound-mini",
]

# Context windows from freellmapi-s2 response
CTX = {
    "freellmapi-auto": 1048576, "fusion": 1048576,
    "gemini-3.5-flash": 1048576, "gpt-oss-120b": 131072,
    "llama-3.3-70b": 131072, "gpt-oss-20b": 131072,
    "gpt-oss-safeguard-20b": 131072, "gemma-4-31b-it": 32768,
    "gemini-2.5-flash": 1048576, "gemma-4-26b-it": 32768,
    "gemini-2.5-flash-lite": 1048576, "llama-3.1-8b-instant": 131072,
    "gemini-3.1-flash-lite": 1048576, "compound": 131072,
    "compound-mini": 131072,
}

async def main():
    conn = await asyncpg.connect(DB_URL)
    now = datetime.now(timezone.utc)
    
    added = 0
    for mid in FREELM_MODELS:
        ctx = CTX.get(mid, 32768)
        
        row = await conn.fetchrow("SELECT availability FROM model_catalog WHERE id = $1", mid)
        if row:
            if row["availability"] == "disabled":
                await conn.execute("UPDATE model_catalog SET availability = 'available', updated_at = now() WHERE id = $1", mid)
                print(f"  ENABLE {mid}")
                added += 1
            else:
                print(f"  SKIP {mid} (already {row['availability']})")
            continue
        
        await conn.execute("""
            INSERT INTO model_catalog (
                id, provider_model_id, provider, display_name, description,
                modalities, capabilities, recommended_for,
                context_window, max_output_tokens,
                currency, input_per_million, output_per_million,
                cached_input_per_million, reasoning_per_million,
                price_version, effective_from,
                availability, audience, provenance, updated_at,
                last_verified_at, rate_limit,
                usd_input_per_million, usd_output_per_million
            ) VALUES (
                $1, $1, 'freellmapi-s2', $1, $2,
                $3::jsonb, $4::jsonb, $5::jsonb,
                $6, 8192,
                'IRT', 0, 0,
                null, null,
                'v1', $7,
                'available', $8::jsonb, 'admin-approved', $7,
                $7, null,
                0, 0
            )
        """, mid, "",
            '{"input": ["text"], "output": ["text"]}',
            '["chat"]', '["chat"]',
            ctx, now,
            '["consumer", "developer"]')
        print(f"  ADD {mid}")
        added += 1
    
    stats = await conn.fetch("SELECT availability, count(*) as cnt FROM model_catalog GROUP BY availability")
    print(f"\nCatalog stats:")
    for r in stats:
        print(f"  {r['availability']}: {r['cnt']}")
    
    await conn.close()
    print(f"\nDone. {added} models added/enabled")

asyncio.run(main())
