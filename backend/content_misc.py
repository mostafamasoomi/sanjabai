"""Public content routes (about/org-default-model/features/discounts), the
admin model-tester, and the signup captcha generator.

Split out of content.py purely to stay under the house 500-line cap --
nothing here changed in the move. Unlike content_catalog.py /
content_eur_rate.py / content_refresh.py, nothing in this file is
monkeypatched by the test suite and nothing here calls back into a
monkeypatch-sensitive `content.<name>`, so there is no IMPORT CONTRACT to
document -- routes below register directly onto `content.router` (imported
plainly at module scope, after content.py has defined it) and otherwise use
only `database`/`models`/`dependencies` imports, same as content.py did
before the split. content.py imports this module purely for its
side-effect of registering these six routes; nothing is re-exported from it.
"""
from __future__ import annotations

import base64
import io
import json
import random
import string

import sqlalchemy
from fastapi import Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from PIL import Image, ImageDraw, ImageFont

from database import async_session, rds, LITELLM_HOST
from models import AboutContent, Feature, Discount, ProxyConfig
from dependencies import admin_required
from i18n import err

import content


@content.router.get('/about')
async def get_about() -> JSONResponse:
    cached = await rds.get('cache:about')
    if cached:
        return JSONResponse(json.loads(cached))
    if async_session is None:
        return JSONResponse({'title': 'درباره ما', 'body': ''})
    async with async_session() as session:
        res = await session.execute(AboutContent.__table__.select())
        row = res.fetchone()
        if not row:
            return JSONResponse({'title': 'درباره ما', 'body': ''})
        result = jsonable_encoder(dict(row._mapping))
    await rds.setex('cache:about', 120, json.dumps(result))
    return JSONResponse(result)


@content.router.get('/org/default-model')
async def get_org_default_model() -> JSONResponse:
    """Public endpoint: get org-wide default model (for chat fallback)."""
    cached = await rds.get('cache:org:default-model')
    if cached:
        return JSONResponse(json.loads(cached))
    if async_session is None:
        return JSONResponse({'default_model': ''})
    async with async_session() as session:
        res = await session.execute(ProxyConfig.__table__.select())
        row = res.fetchone()
        dm = row.default_model if row and hasattr(row, 'default_model') else ''
        result = {'default_model': dm}
    await rds.setex('cache:org:default-model', 120, json.dumps(result))
    return JSONResponse(result)


@content.router.get('/content/features')
async def public_features() -> JSONResponse:
    cached = await rds.get('cache:content:features')
    if cached:
        return JSONResponse(json.loads(cached))
    if async_session is None:
        return JSONResponse([])
    async with async_session() as session:
        res = await session.execute(Feature.__table__.select().where(Feature.active == True).order_by(Feature.order_idx))
        rows = [dict(r._mapping) for r in res.fetchall()]
    result = jsonable_encoder(rows)
    await rds.setex('cache:content:features', 120, json.dumps(result))
    return JSONResponse(result)


@content.router.get('/content/discounts')
async def public_discounts() -> JSONResponse:
    cached = await rds.get('cache:content:discounts')
    if cached:
        return JSONResponse(json.loads(cached))
    if async_session is None:
        return JSONResponse([])
    async with async_session() as session:
        res = await session.execute(Discount.__table__.select().where(Discount.active == True))
        rows = [{'code': r.code, 'percent': r.percent} for r in res.fetchall()]
    result = jsonable_encoder(rows)
    await rds.setex('cache:content:discounts', 120, json.dumps(result))
    return JSONResponse(result)


# ── Model Test (auto-recommend healthy) ──


# ponytail: test all models + auto-recommend healthy ones (concurrent)
@content.router.get("/admin/test-models")
async def test_all_models(request: Request):
    """Ping every model concurrently, return status, and mark healthy ones as recommended."""
    # This route was reachable by ANY anonymous caller until 2026-08-23 -- it is
    # named /admin/* and sits beside other /admin/ routes that do check, so the
    # missing gate read as an oversight rather than a decision. Two things made
    # it expensive rather than merely untidy- it fires one real upstream chat
    # completion per available model (25 at the time) on every call, so anyone
    # could burn provider money in a loop, squarely against "no request may be
    # loss-making" -- and it then WRITES to the production catalog
    # (UPDATE model_catalog SET recommended_for), so an anonymous request could
    # change which models we recommend to real users. Verified open on
    # production before this fix- an unauthenticated GET returned 200.
    if not await admin_required(request):
        return err('دسترسی مدیر لازم است', 'Admin access required.', 403)
    import httpx, asyncio
    async with async_session() as session:
        res = await session.execute(sqlalchemy.text(
            "SELECT provider_model_id, display_name FROM model_catalog WHERE availability='available'"
        ))
        rows = res.fetchall()

    async def test_one(client, row):
        mid, name = row.provider_model_id, row.display_name
        try:
            r = await client.post(
                f"{LITELLM_HOST}/v1/chat/completions",
                json={"model": mid, "messages": [{"role":"user","content":"hi"}], "max_tokens": 5},
                headers={}
            )
            ok = r.status_code == 200
            return {"id": mid, "name": name, "ok": ok, "status": r.status_code, "ms": r.elapsed.total_seconds() * 1000}
        except Exception as e:
            return {"id": mid, "name": name, "ok": False, "error": str(e)[:100]}

    async with httpx.AsyncClient(timeout=10) as client:
        results = await asyncio.gather(*[test_one(client, row) for row in rows])

    healthy_ids = [r["id"] for r in results if r["ok"]]
    if healthy_ids:
        async with async_session() as session:
            for mid in healthy_ids:
                await session.execute(
                    sqlalchemy.text("UPDATE model_catalog SET recommended_for = '[\"chat\"]' WHERE provider_model_id = :mid"),
                    {"mid": mid}
                )
            await session.commit()
        await rds.delete('cache:catalog:models')

    return JSONResponse({"results": results, "total": len(results), "ok": len(healthy_ids), "recommended": len(healthy_ids)})

# ponytail: image captcha generator

@content.router.get("/captcha")
async def captcha_image(request: Request):
    """Generate a professional alphanumeric captcha image."""

    # 5 random characters (uppercase and digits, excluding ambiguous ones like O, 0, I, 1)
    chars = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    answer = "".join(random.choices(chars, k=5))

    # Store answer in redis for 5 minutes
    token = base64.urlsafe_b64encode(f"{random.getrandbits(64)}".encode()).decode()[:12]
    await rds.setex(f"captcha:{token}", 300, answer)

    W, H = 200, 70
    # Background color (off-white for contrast)
    img = Image.new("RGB", (W, H), (245, 245, 250))
    draw = ImageDraw.Draw(img)

    # Load font with fallback chain
    font = None
    for font_path in [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
    ]:
        try:
            font = ImageFont.truetype(font_path, 42)
            break
        except Exception:
            continue
    if font is None:
        font = ImageFont.load_default()

    # Draw noise lines and arcs
    for _ in range(5):
        x1, y1 = random.randint(0, W), random.randint(0, H)
        x2, y2 = random.randint(0, W), random.randint(0, H)
        draw.line([(x1, y1), (x2, y2)], fill=(random.randint(100, 200), random.randint(100, 200), random.randint(100, 200)), width=random.randint(1, 3))

    for _ in range(4):
        x1, y1 = random.randint(-50, W), random.randint(-50, H)
        x2, y2 = random.randint(x1, W+50), random.randint(y1, H+50)
        draw.arc([x1, y1, x2, y2], random.randint(0, 180), random.randint(180, 360), fill=(random.randint(100, 200), random.randint(100, 200), random.randint(100, 200)), width=random.randint(1, 3))

    # Draw individual characters with rotation and slight jitter
    x_offset = 15
    for char in answer:
        # Create a blank image for the char
        char_img = Image.new("RGBA", (45, 60), (255, 255, 255, 0))
        char_draw = ImageDraw.Draw(char_img)
        char_color = (random.randint(20, 80), random.randint(20, 80), random.randint(20, 80))
        # NOTE: this is PIL's ImageDraw.text() -- draws the captcha glyph onto
        # the image -- NOT SQLAlchemy's sqlalchemy.text(). A static SQL
        # auditing tool has previously false-positived on this exact line;
        # do not "fix" it. See content.py's former docstring / NEXT-SESSION.
        char_draw.text((0, 0), char, font=font, fill=char_color)

        # Rotate
        char_img = char_img.rotate(random.randint(-30, 30), expand=1, resample=Image.BICUBIC)

        # Paste into main image
        y_offset = random.randint(0, 10)
        img.paste(char_img, (x_offset, y_offset), char_img)
        x_offset += random.randint(30, 36)

    # Add dot noise
    for _ in range(120):
        x, y = random.randint(0, W-1), random.randint(0, H-1)
        draw.point((x, y), fill=(random.randint(50, 150), random.randint(50, 150), random.randint(50, 150)))

    buf = io.BytesIO()
    img.save(buf, "PNG")
    b64 = base64.b64encode(buf.getvalue()).decode()

    return JSONResponse({"captcha": f"data:image/png;base64,{b64}", "token": token})
