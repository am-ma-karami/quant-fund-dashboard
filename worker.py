import logging
import sys

from apscheduler.schedulers.blocking import BlockingScheduler

from core.database import engine, Base
from services.fund_sync import sync_funds_pipeline
from services.tasks import update_etf_market_data
from services.history_bootstrap import backfill_single_fund


logging.basicConfig(
    stream=sys.stdout,
    level=logging.INFO,
    format="%(asctime)s - [%(levelname)s] - %(name)s : %(message)s"
)

logger = logging.getLogger("WORKER")

Base.metadata.create_all(bind=engine)


STOCK_FUND_TYPE = 6


def run_fund_sync():
    try:
        logger.info("Starting all fund sync...")
        sync_funds_pipeline()
        logger.info("All fund sync completed.")
    except Exception:
        logger.exception("All fund sync failed.")


def run_stock_fund_sync():
    try:
        logger.info("Starting stock fund sync...")
        sync_funds_pipeline(fund_types=[STOCK_FUND_TYPE])
        logger.info("Stock fund sync completed.")
    except Exception:
        logger.exception("Stock fund sync failed.")


def run_etf_sync():
    try:
        logger.info("Starting ETF sync...")
        update_etf_market_data()
        logger.info("ETF sync completed.")
    except Exception:
        logger.exception("ETF sync failed.")


def run_history_backfill():
    try:
        logger.info("Starting history backfill (single fund)...")
        backfill_single_fund()
        logger.info("History backfill completed.")
    except Exception:
        logger.exception("History backfill failed.")


if __name__ == "__main__":
    logger.info("Starting Quant Worker Service...")

    run_fund_sync()
    run_etf_sync()
    run_history_backfill()

    scheduler = BlockingScheduler()

    scheduler.add_job(
        run_stock_fund_sync,
        "interval",
        minutes=1,
        id="stock_fund_sync",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=60,
    )

    scheduler.add_job(
        run_etf_sync,
        "interval",
        minutes=1,
        id="etf_sync",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=60,
    )

    scheduler.add_job(
        run_history_backfill,
        "interval",
        seconds=10,
        id="history_backfill",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=30,
    )

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Worker stopped.")
