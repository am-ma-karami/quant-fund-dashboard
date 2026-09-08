import logging
import sys

from apscheduler.schedulers.blocking import BlockingScheduler

from core.database import engine, Base
from services.fund_sync import sync_funds_pipeline
from services.tasks import update_etf_market_data


logging.basicConfig(
    stream=sys.stdout,
    level=logging.INFO,
    format="%(asctime)s - [%(levelname)s] - %(name)s : %(message)s"
)

logger = logging.getLogger("WORKER")

Base.metadata.create_all(bind=engine)


def run_fund_sync():
    try:
        logger.info("Starting fund sync...")
        sync_funds_pipeline()
        logger.info("Fund sync completed.")
    except Exception:
        logger.exception("Fund sync failed.")


def run_etf_sync():
    try:
        logger.info("Starting ETF sync...")
        update_etf_market_data()
        logger.info("ETF sync completed.")
    except Exception:
        logger.exception("ETF sync failed.")


if __name__ == "__main__":
    logger.info("Starting Quant Worker Service...")

    run_fund_sync()
    run_etf_sync()

    scheduler = BlockingScheduler()

    scheduler.add_job(
        run_fund_sync,
        "interval",
        minutes=5,
        id="fund_sync",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=120,
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

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Worker stopped.")