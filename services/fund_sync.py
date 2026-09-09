import logging
from datetime import datetime, timedelta
from dateutil import parser
from core.database import SessionLocal
from core.repositories import FundRepository
from core.models import SyncStatus
from services.providers import TSETMCProvider
from services.preprocessing import clean_fund_data
from services.cache_service import invalidate_dashboard_cache
from services.data_quality import calculate_coverage, calculate_quality_score

logger = logging.getLogger(__name__)
provider = TSETMCProvider()
FUND_TYPES = [4, 5, 6, 7, 11, 12, 13, 14, 16, 17]


def sync_funds_pipeline(
    fund_types: list[int] | None = None,
):
    if fund_types is None:
        fund_types = FUND_TYPES

    logger.info("Starting Data Pipeline Sync...")

    db = SessionLocal()
    fund_repo = FundRepository(db)

    started_at = datetime.utcnow()

    try:
        total_expected = 0
        total_received = 0
        total_valid = 0
        total_failed = 0

        for f_type in fund_types:
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

            total_expected += len(funds_data)

            for item in funds_data:
                total_received += 1

                try:
                    clean_item = clean_fund_data(item)

                    reg_no = clean_item["reg_no"]

                    if not reg_no:
                        total_failed += 1
                        continue

                    fund_repo.upsert_fund(
                        reg_no,
                        clean_item["name"],
                        f_type,
                        clean_item
                    )

                    fund = fund_repo.get_fund_by_reg_no(reg_no)

                    if fund and (not fund.symbol or not fund.sector):
                        identity = provider.fetch_instrument_identity(reg_no)

                        if identity:
                            fund.symbol = identity.get("symbol") or identity.get("lVal18AFC")
                            fund.sector = identity.get("sector") or identity.get("sectorName")
                            fund.subsector = identity.get("subSector") or identity.get("subSectorName")
                            fund.market = identity.get("market")
                            fund.instrument_status = identity.get("status")

                    record_date_str = item.get("recordDate")

                    if record_date_str:
                        observed_at = parser.parse(record_date_str)

                        fund_repo.upsert_fund_history(
                            reg_no=reg_no,
                            nav_stat=clean_item["nav_stat"],
                            nav_sub=clean_item["nav_sub"],
                            nav_red=clean_item["nav_red"],
                            net_asset=clean_item["net_asset"],
                            units=clean_item["units"],
                            observed_at=observed_at
                        )

                    total_valid += 1

                except Exception:
                    total_failed += 1
                    logger.exception(
                        "Failed processing fund item"
                    )
                    continue

        db.commit()

        coverage = calculate_coverage(
            expected=total_expected,
            received=total_received,
        )

        quality_score = calculate_quality_score(
            expected=total_expected,
            received=total_received,
            valid=total_valid,
            failed=total_failed,
        )

        status = db.query(SyncStatus).filter(
            SyncStatus.job_name == "fund_sync"
        ).first()
        if not status:
            status = SyncStatus(job_name="fund_sync")
            db.add(status)

        status.status = "healthy" if total_failed == 0 else "partial"
        status.started_at = started_at
        status.finished_at = datetime.utcnow()
        status.expected_count = total_expected
        status.received_count = total_received
        status.valid_count = total_valid
        status.updated_count = total_valid
        status.failed_count = total_failed
        status.quality_score = quality_score
        status.duration_ms = int((datetime.utcnow() - started_at).total_seconds() * 1000)
        status.last_success_at = datetime.utcnow() if total_failed == 0 else status.last_success_at
        status.provider = "TSETMC"
        status.error_message = None if total_failed == 0 else f"{total_failed} funds failed validation"

        db.commit()

        invalidate_dashboard_cache()

        logger.info(
            "Pipeline Sync Completed. Updated %s funds. Coverage: %.1f%%",
            total_valid,
            coverage * 100
        )

    except Exception:
        db.rollback()
        logger.exception("Pipeline Error")

    finally:
        db.close()
