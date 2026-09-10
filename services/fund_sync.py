import logging
from datetime import datetime, timedelta
from dateutil import parser
from core.database import SessionLocal
from core.repositories import FundRepository, DataQualityRepository
from core.models import Fund, SyncStatus
from services.providers import TSETMCProvider
from services.preprocessing import clean_fund_data
from services.cache_service import invalidate_dashboard_cache
from services.data_quality import calculate_coverage, calculate_quality_score
from services.validation import (
    validate_live_record,
    SEVERITY_CRITICAL,
)

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

        # NAV قبلی هر صندوق — برای اعتبارسنجی حرکت غیرعادی، در یک کوئری
        prev_nav_map = {
            reg_no: nav
            for reg_no, nav in db.query(Fund.reg_no, Fund.nav_stat).all()
        }

        # تخلف‌های این چرخه — یکجا در پایان ثبت می‌شوند
        cycle_issues = []

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

                    record_date_str = item.get("recordDate")
                    observed_at = (
                        parser.parse(record_date_str)
                        if record_date_str
                        else started_at
                    )

                    # اعتبارسنجی: تخلف بحرانی → قرنطینه (عدم ذخیره این چرخه)
                    issues = validate_live_record(
                        reg_no=reg_no,
                        nav=clean_item["nav_stat"],
                        units=clean_item["units"],
                        net_asset=clean_item["net_asset"],
                        prev_nav=prev_nav_map.get(reg_no),
                        observed_at=observed_at,
                    )

                    if any(
                        issue.severity == SEVERITY_CRITICAL
                        for issue in issues
                    ):
                        total_failed += 1
                        cycle_issues.extend(issues)
                        logger.warning(
                            "Quarantined fund %s: %s",
                            reg_no,
                            "; ".join(issue.detail for issue in issues),
                        )
                        continue

                    cycle_issues.extend(issues)

                    fund_repo.upsert_fund(
                        reg_no,
                        clean_item["name"],
                        f_type,
                        clean_item
                    )

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

        DataQualityRepository(db).record_issues(cycle_issues)

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
