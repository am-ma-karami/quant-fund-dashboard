"""سینک تاریخچه شاخص کل بورس (TEDPIX) در جدول benchmark_histories.

این ماژول داده شاخص را به‌صورت افزایشی ذخیره می‌کند: فقط مشاهداتی
که از آخرین تاریخ ذخیره‌شده جدیدتر هستند upsert می‌شوند.
"""
import logging

from core.database import SessionLocal
from core.models import BenchmarkHistory
from core.repositories import BenchmarkRepository
from core.benchmark import TEHRAN_TOTAL_INDEX
from services.providers import TSETMCProvider, parse_tsetmc_date


logger = logging.getLogger(__name__)

provider = TSETMCProvider()


def _latest_stored_date(db) -> object | None:
    return (
        db.query(BenchmarkHistory.observed_at)
        .filter(
            BenchmarkHistory.benchmark_code == TEHRAN_TOTAL_INDEX.code
        )
        .order_by(BenchmarkHistory.observed_at.desc())
        .first()
    )


def sync_benchmark_history():
    """دریافت تاریخچه شاخص کل و ذخیره افزایشی مشاهدات جدید."""
    db = SessionLocal()
    repo = BenchmarkRepository(db)

    try:
        history = provider.fetch_index_history(TEHRAN_TOTAL_INDEX.code)

        if not history:
            logger.warning("No benchmark history returned from provider")
            return

        latest_row = _latest_stored_date(db)
        latest = latest_row[0] if latest_row else None

        new_rows = 0
        skipped = 0

        for item in history:
            observed_at = parse_tsetmc_date(item.get("dEven"))
            value = item.get("xNivInuClMresIbs")

            if observed_at is None or value is None:
                skipped += 1
                continue

            if latest is not None and observed_at <= latest:
                continue

            repo.upsert_history(
                benchmark_code=TEHRAN_TOTAL_INDEX.code,
                benchmark_name=TEHRAN_TOTAL_INDEX.name,
                value=float(value),
                observed_at=observed_at,
            )
            new_rows += 1

        db.commit()

        logger.info(
            "Benchmark sync completed: %s new observations (%s skipped)",
            new_rows,
            skipped,
        )

    except Exception:
        db.rollback()
        logger.exception("Benchmark sync failed")

    finally:
        db.close()
