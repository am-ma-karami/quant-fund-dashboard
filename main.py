import os
import sys
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from redis import asyncio as aioredis
from fastapi_cache import FastAPICache
from fastapi_cache.backends.redis import RedisBackend

from core.database import engine, Base
from routers.web import router


logging.basicConfig(
    stream=sys.stdout,
    level=logging.INFO,
    format="%(asctime)s - [%(levelname)s] - %(name)s : %(message)s"
)


Base.metadata.create_all(bind=engine)


@asynccontextmanager
async def lifespan(app: FastAPI):
    redis_url = os.getenv(
        "REDIS_URL",
        "redis://localhost:6379/0"
    )

    redis = aioredis.from_url(
        redis_url,
        encoding="utf8",
        decode_responses=True
    )

    FastAPICache.init(
        RedisBackend(redis),
        prefix="quant_cache"
    )

    logging.getLogger("APP").info(
        "Web application started successfully"
    )

    yield

    await redis.close()


app = FastAPI(
    title="Quant Fund Dashboard",
    description="Live Dashboard for TSETMC Funds and ETFs",
    version="2.0.0",
    lifespan=lifespan
)

app.include_router(router)