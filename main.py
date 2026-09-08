import os
import sys           # <--- اضافه شد
import logging       # <--- اضافه شد
from contextlib import asynccontextmanager
from fastapi import FastAPI
from apscheduler.schedulers.background import BackgroundScheduler
from redis import asyncio as aioredis
from fastapi_cache import FastAPICache
from fastapi_cache.backends.redis import RedisBackend

from core.database import engine, Base
from services.tasks import update_funds_data, update_etf_market_data
from routers.web import router

# --- پیکربندی استاندارد لاگ‌ها برای نمایش در کنسول داکر ---
logging.basicConfig(
    stream=sys.stdout,
    level=logging.INFO,
    format="%(asctime)s - [%(levelname)s] - %(name)s : %(message)s"
)
# ------------------------------------------------------------

Base.metadata.create_all(bind=engine)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # اتصال به Redis
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    redis = aioredis.from_url(redis_url, encoding="utf8", decode_responses=True)
    FastAPICache.init(RedisBackend(redis), prefix="quant_cache")
    
    # دریافت اولیه دیتا
    update_funds_data()
    update_etf_market_data()
    
    # راه‌اندازی زمان‌بند
    scheduler = BackgroundScheduler()
    scheduler.add_job(update_funds_data, 'interval', minutes=1)
    scheduler.add_job(update_etf_market_data, 'interval', minutes=1)
    scheduler.start()
    
    yield
    
    scheduler.shutdown()
    await redis.close() 

app = FastAPI(
    title="Quant Fund Dashboard",
    description="Live Dashboard for TSETMC Funds and ETFs",
    version="1.0.0",
    lifespan=lifespan
)

app.include_router(router)