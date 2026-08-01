#!/usr/bin/env python3
import asyncio
import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select
from models import Base, Pricing, Feature, Discount, AboutContent, ProxyConfig

DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql+asyncpg://sanjhubai:sanjhubai@127.0.0.1:5432/sanjhubai')

def get_engine():
    return create_async_engine(DATABASE_URL)

async def init_db():
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    async_session = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    
    async with async_session() as session:
        # Pricing
        models = [
            {"model": "kr/gpt-4o-mini", "input_per_million": 2, "output_per_million": 6, "currency": "IRT"},
            {"model": "kr/claude-3.5-sonnet", "input_per_million": 10, "output_per_million": 30, "currency": "IRT"},
            {"model": "kr/gpt-4o", "input_per_million": 15, "output_per_million": 45, "currency": "IRT"},
            {"model": "kr/llama-3.1-405b", "input_per_million": 5, "output_per_million": 15, "currency": "IRT"},
        ]
        for m in models:
            stmt = select(Pricing).where(Pricing.model == m["model"])
            res = await session.execute(stmt)
            if not res.scalar_one_or_none():
                session.add(Pricing(**m))
        
        # Features
        features = [
            {"title": "چت هوشمند", "description": "دسترسی به جدیدترین مدلهای هوش مصنوعی برای چت و پاسخگویی", "icon": "💬", "order_idx": 1, "active": True},
            {"title": "سرعت بالا", "description": "پاسخگویی در کمتر از ۱ ثانیه با زیرساخت بهینه", "icon": "⚡", "order_idx": 2, "active": True},
            {"title": "پشتیبانی فارسی", "description": "پشتیبانی کامل از زبان فارسی و لهجه‌های مختلف", "icon": "🇮🇷", "order_idx": 3, "active": True},
            {"title": "حریم خصوصی", "description": "عدم ذخیره‌سازی مکالمات و حفظ حریم خصوصی کاربران", "icon": "🔒", "order_idx": 4, "active": True},
        ]
        for f in features:
            stmt = select(Feature).where(Feature.title == f["title"])
            res = await session.execute(stmt)
            if not res.scalar_one_or_none():
                session.add(Feature(**f))
        
        # Discounts
        discounts = [
            {"code": "WELCOME10", "percent": 10, "active": True},
            {"code": "SUMMER20", "percent": 20, "active": True},
        ]
        for d in discounts:
            stmt = select(Discount).where(Discount.code == d["code"])
            res = await session.execute(stmt)
            if not res.scalar_one_or_none():
                session.add(Discount(**d))
        
        # About
        stmt = select(AboutContent)
        res = await session.execute(stmt)
        if not res.scalar_one_or_none():
            session.add(AboutContent(title="درباره ما", body="ما یک پلتفرم هوش مصنوعی فارسی هستیم که با هدف ارائه بهترین تجربه کاربری و دسترسی به جدیدترین مدلهای هوش مصنوعی ایجاد شده‌ایم. تیم ما متشکل از متخصصان حوزه فناوری و هوش مصنوعی است که با عشق به زبان فارسی و فرهنگ ایرانی، این پلتفرم را توسعه داده‌اند."))
        
        # Proxy
        # NOTE: this credential is hardcoded and has been sitting in git
        # history — flagged separately as needing rotation, independent of
        # this rename. Only the hostname changed here.
        stmt = select(ProxyConfig)
        res = await session.execute(stmt)
        if not res.scalar_one_or_none():
            session.add(ProxyConfig(proxy_url="socks5://ted:T%23d%40123234@sanjhubai_tunnel:9090", proxy_type="socks5", active=True))
        
        await session.commit()

if __name__ == "__main__":
    asyncio.run(init_db())
    print("✅ Database initialized with sample data")