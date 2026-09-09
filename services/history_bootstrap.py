import logging
import time
from datetime import timedelta

from dateutil import parser

from core.database import SessionLocal
from core.repositories import FundRepository, iran_time
from services.providers import TSETMCProvider

from sqlalchemy import func
from core.database import SessionLocal
from core.repositories import FundRepository
from core.models import Fund, FundHistory
from dateutil import parser
import logging



logger = logging.getLogger(__name__)

provider = TSETMCProvider()
HISTORY_DAYS = 30
INITIAL_HISTORY_RECORDS = 3
STALE_SOURCE_RETRY_HOURS = 6


def _recent_history_records(history_data: list, days: int, limit: int) -> list:
    """Keep valid observations from the actual recent calendar window."""
    cutoff = iran_time() - timedelta(days=days)
    records = []
    for item in history_data:
        record_date = item.get("recordDate")
        if not record_date:
            continue
        try:
            observed_at = parser.parse(record_date).replace(tzinfo=None)
        except (TypeError, ValueError, OverflowError):
            logger.warning("Skipping an invalid history date: %r", record_date)
            continue
        if observed_at >= cutoff:
            records.append((observed_at, item))
    return sorted(records, key=lambda record: record[0])[-limit:]


def _history_records_for_backfill(history_data: list, days: int, limit: int) -> tuple[list, str]:
    """Prefer the current window, falling back to the latest source observations."""
    recent = _recent_history_records(history_data, days, limit)
    if len(recent) >= limit:
        return recent, "recent"

    all_records = []
    for item in history_data:
        record_date = item.get("recordDate")
        if not record_date:
            continue
        try:
            all_records.append((parser.parse(record_date).replace(tzinfo=None), item))
        except (TypeError, ValueError, OverflowError):
            logger.warning("Skipping an invalid history date: %r", record_date)
    return sorted(all_records, key=lambda record: record[0])[-limit:], "latest_available"


def bootstrap_fund_history(reg_no: int, days: int = HISTORY_DAYS):
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

        records, _ = _history_records_for_backfill(history_data, days, days)
        for observed_at, item in records:

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



def backfill_single_fund():
    """
    پیدا کردن خودکار یک صندوق که تاریخچه ناقص دارد (کمتر از 90 روز)
    و تکمیل دیتای آن از طریق API بورس.
    """
    db = SessionLocal()
    fund_repo = FundRepository(db)
    
    # مقداردهی اولیه برای اینکه در بخش except خطای NameError نگیریم
    reg_no = "نامشخص" 
    
    try:
        # ۱. کوئری هوشمند برای پیدا کردن صندوقی که تاریخچه ندارد یا ناقص است
        # شمردن تعداد رکوردهای هیستوری برای هر صندوق
        subquery = db.query(
            FundHistory.fund_reg_no, 
            func.count(FundHistory.id).label('history_count')
        ).group_by(FundHistory.fund_reg_no).subquery()
        
        # پیدا کردن صندوقی که یا هیستوری ندارد (None) یا تعدادش کمتر از 90 است
        fund_to_backfill = db.query(Fund).outerjoin(
            subquery, Fund.reg_no == subquery.c.fund_reg_no
        ).filter(
            (subquery.c.history_count == None) | (subquery.c.history_count < 90)
        ).first()
        
        if not fund_to_backfill:
            logger.info("All funds have complete 90-day history. Nothing to backfill.")
            return

        # ۲. استخراج reg_no و گرفتن دیتا از API
        reg_no = fund_to_backfill.reg_no
        logger.info(f"Backfilling history for Fund {reg_no}...")
        
        history_data = provider.fetch_fund_history_detail(reg_no)
        
        if not history_data:
            logger.warning(f"No history data returned for Fund {reg_no}")
            return

        # ۳. ذخیره 90 روز آخر
        for item in history_data[:90]:
            record_date = item.get("recordDate")
            if not record_date: 
                continue
            
            observed_at = parser.parse(record_date)
            
            fund_repo.upsert_fund_history(
                reg_no=reg_no,
                nav_stat=item.get("navStat") or 0.0,
                net_asset=item.get("netAsset") or 0.0,
                observed_at=observed_at
            )
            
        db.commit()
        logger.info(f"Successfully backfilled history for Fund {reg_no}.")
        
    except Exception as e:
        db.rollback()
        # حالا اینجا reg_no مقدار دارد و ارور نمی‌دهد
        logger.error(f"Error backfilling fund {reg_no}: {e}")
    finally:
        db.close()
