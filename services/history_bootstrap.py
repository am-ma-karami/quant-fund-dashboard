import logging
import time

from dateutil import parser

from core.database import SessionLocal
from core.repositories import FundRepository
from services.providers import TSETMCProvider


logger = logging.getLogger(__name__)

provider = TSETMCProvider()


def bootstrap_fund_history(reg_no: int, days: int = 90):
    db = SessionLocal()
    repo = FundRepository(db)

    try:
        if repo.has_history(reg_no):
            logger.info(
                "History already exists for fund %s",
                reg_no
            )
            return

        logger.info(
            "Bootstrapping history for fund %s",
            reg_no
        )

        history_data = provider.fetch_fund_history_detail(
            reg_no
        )

        if not history_data:
            logger.warning(
                "No history returned for fund %s",
                reg_no
            )
            return

        for item in history_data:

            record_date = item.get("recordDate")

            if not record_date:
                continue

            observed_at = parser.parse(record_date)

            repo.upsert_fund_history(
                reg_no=reg_no,
                nav_stat=item.get("navStat") or 0.0,
                net_asset=item.get("netAsset") or 0.0,
                observed_at=observed_at
            )

        db.commit()

        logger.info(
            "History bootstrap completed for fund %s",
            reg_no
        )

    except Exception:
        db.rollback()
        logger.exception(
            "History bootstrap failed for fund %s",
            reg_no
        )

    finally:
        db.close()


def backfill_single_fund(min_history_days: int = 30):
    """
    Backfill history for ONE fund that has less than min_history_days of data.
    Returns True if a fund was processed, False if no funds need backfill.
    """
    db = SessionLocal()
    repo = FundRepository(db)

    try:
        funds = repo.get_funds_with_insufficient_history(
            min_days=min_history_days,
            limit=1
        )

        if not funds:
            logger.info("No funds require history backfill (all have >= %s days)", min_history_days)
            return False

        fund = funds[0]
        logger.info(
            "Backfilling history for Fund %s (currently %s records)",
            fund.reg_no,
            repo.get_history_count(fund.reg_no)
        )

        history_data = provider.fetch_fund_history_detail(
            fund.reg_no
        )

        if not history_data:
            logger.warning("No history data returned for Fund %s", fund.reg_no)
            return True

        count = 0
        for item in history_data:
            record_date = item.get("recordDate")
            if not record_date:
                continue

            observed_at = parser.parse(record_date)

            # Only insert if we don't already have this date
            existing = repo.get_history_by_date(fund.reg_no, observed_at)
            if not existing:
                repo.upsert_fund_history(
                    reg_no=fund.reg_no,
                    nav_stat=item.get("navStat") or 0.0,
                    net_asset=item.get("netAsset") or 0.0,
                    observed_at=observed_at,
                )
                count += 1

        db.commit()

        logger.info(
            "Added %s new history records for Fund %s (total now: %s)",
            count,
            fund.reg_no,
            repo.get_history_count(fund.reg_no)
        )
        return True

    except Exception:
        db.rollback()
        logger.exception(
            "History backfill failed for Fund %s",
            fund.reg_no if 'fund' in locals() else 'unknown'
        )
        return True

    finally:
        db.close()