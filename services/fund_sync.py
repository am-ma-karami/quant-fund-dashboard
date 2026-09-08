import logging
from datetime import datetime, timedelta
from dateutil import parser # pip install python-dateutil
from core.database import SessionLocal
from core.repositories import FundRepository
from services.providers import TSETMCProvider
from services.preprocessing import clean_fund_data
from services.cache_service import invalidate_dashboard_cache

logger = logging.getLogger(__name__)
provider = TSETMCProvider()
FUND_TYPES = [4, 5, 6, 7, 11, 12, 13, 14, 16, 17]

def sync_funds_pipeline():
    logger.info("Starting Data Pipeline Sync...")

    db = SessionLocal()
    fund_repo = FundRepository(db)

    try:
        total_updated = 0

        for f_type in FUND_TYPES:

            logger.info(
                "Fetching funds for category %s",
                f_type
            )

            funds_data = provider.fetch_funds_by_type(f_type)

            if not funds_data:
                logger.warning(
                    "No funds returned for category %s",
                    f_type
                )
                continue

            for item in funds_data:

                try:
                    clean_item = clean_fund_data(item)

                    reg_no = clean_item["reg_no"]

                    if not reg_no:
                        continue

                    fund_repo.upsert_fund(
                        reg_no,
                        clean_item["name"],
                        f_type,
                        clean_item
                    )

                    record_date_str = item.get("recordDate")

                    if record_date_str:
                        observed_at = parser.parse(record_date_str)

                        fund_repo.upsert_fund_history(
                            reg_no=reg_no,
                            nav_stat=clean_item["nav_stat"],
                            net_asset=clean_item["net_asset"],
                            observed_at=observed_at
                        )

                    total_updated += 1

                except Exception:
                    logger.exception(
                        "Failed processing fund item"
                    )
                    continue

        db.commit()
        
        invalidate_dashboard_cache()

        logger.info(
            "Pipeline Sync Completed. Updated %s funds.",
            total_updated
        )

    except Exception:
        db.rollback()
        logger.exception("Pipeline Error")

    finally:
        db.close()