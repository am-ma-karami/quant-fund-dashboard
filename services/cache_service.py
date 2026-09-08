import os
from redis import Redis


REDIS_URL = os.getenv(
    "REDIS_URL",
    "redis://localhost:6379/0"
)


redis = Redis.from_url(
    REDIS_URL,
    decode_responses=True
)


def invalidate_dashboard_cache():
    keys = [
        "quant_cache:/api/dashboard/top-funds",
        "quant_cache:/api/dashboard/heatmap",
        "quant_cache:/api/market-pulse",
    ]

    for key in keys:
        try:
            redis.delete(key)
        except Exception:
            pass