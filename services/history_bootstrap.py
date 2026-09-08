import logging

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

        for item in history_data[:days]:

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