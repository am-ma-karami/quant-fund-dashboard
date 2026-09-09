import logging
import time
from datetime import datetime, timedelta

from dateutil import parser

from core.database import SessionLocal
from core.repositories import FundRepository, iran_time
from services.providers import TSETMCProvider

from sqlalchemy import func
from core.database import SessionLocal
from core.repositories import FundRepository
from core.models import Fund, FundHistory, ETFMarketHistory
from dateutil import parser
import logging
from sqlalchemy.dialects.postgresql import insert as pg_insert



logger = logging.getLogger(__name__)

provider = TSETMCProvider()
HISTORY_DAYS = 30
INITIAL_HISTORY_RECORDS = 3
STALE_SOURCE_RETRY_HOURS = 6


def parse_tsetmc_date(value) -> datetime | None:
    """Parse TSETMC date format YYYYMMDD into datetime."""
    if value is None:
        return None

    value = str(value)

    if len(value) != 8 or not value.isdigit():
        return None

    try:
        return datetime.strptime(value, "%Y%m%d")
    except ValueError:
        return None


def _recent_history_records(history_data: list, days: int, limit: int) -> list:
    """Keep valid observations from the actual recent calendar window."""
    cutoff = iran_time() - timedelta(days=days)
    records = []
    for item in history_data:
        record_date = item.get("recordDate")
        if not record_date:
            continue
        observed_at = parse_tsetmc_date(record_date)
        if observed_at is None:
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
        observed_at = parse_tsetmc_date(record_date)
        if observed_at is None:
            logger.warning("Skipping an invalid history date: %r", record_date)
            continue
        all_records.append((observed_at, item))
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
                nav_stat=item.get("navStat"),
                nav_sub=item.get("navSub"),
                nav_red=item.get("navRed"),
                net_asset=item.get("netAsset"),
                units=item.get("units"),
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
    پیدا کردن خودکار چند صندوق که تاریخچه ناقص دارد (کمتر از 90 روز)
    و تکمیل دیتای آن‌ها از طریق API بورس.
    """
    db = SessionLocal()
    fund_repo = FundRepository(db)
    
    try:
        subquery = db.query(
            FundHistory.fund_reg_no, 
            func.count(FundHistory.id).label('history_count')
        ).group_by(FundHistory.fund_reg_no).subquery()
        
        funds_to_backfill = db.query(Fund).outerjoin(
            subquery, Fund.reg_no == subquery.c.fund_reg_no
        ).filter(
            (subquery.c.history_count == None) | (subquery.c.history_count < 90)
        ).limit(10).all()
        
        if not funds_to_backfill:
            logger.info("All funds have complete 90-day history. Nothing to backfill.")
            return

        for fund_to_backfill in funds_to_backfill:
            reg_no = fund_to_backfill.reg_no
            logger.info(f"Backfilling history for Fund {reg_no}...")
            
            history_data = provider.fetch_fund_history_detail(reg_no)
            
            if not history_data:
                logger.warning(f"No history data returned for Fund {reg_no}")
                continue

            parsed_history = []

            for item in history_data:
                observed_at = parse_tsetmc_date(
                    item.get("recordDate")
                )

                if observed_at is None:
                    continue

                parsed_history.append(
                    (observed_at, item)
                )

            parsed_history.sort(
                key=lambda item: item[0],
                reverse=True,
            )

            for observed_at, item in parsed_history[:90]:
                fund_repo.upsert_fund_history(
                    reg_no=reg_no,
                    nav_stat=item.get("navStat"),
                    nav_sub=item.get("navSub"),
                    nav_red=item.get("navRed"),
                    net_asset=item.get("netAsset"),
                    units=item.get("units"),
                    observed_at=observed_at,
                )

            db.commit()
            logger.info(f"Successfully backfilled history for Fund {reg_no}.")

            fund_obj = fund_repo.get_fund_by_reg_no(reg_no)

            if fund_obj and fund_obj.is_etf and fund_obj.ins_code:
                logger.info(
                    "Backfilling ETF market history for %s",
                    fund_obj.ins_code,
                )

                etf_history = provider.fetch_etf_history(
                    fund_obj.ins_code,
                    limit=0,
                )

                cutoff = iran_time() - timedelta(days=90)

                records = []

                for item in etf_history:
                    observed_at = parse_tsetmc_date(
                        item.get("dEven")
                    )

                    if observed_at is None:
                        continue

                    if observed_at < cutoff:
                        continue

                    last_price = item.get("pDrCotVal")
                    closing_price = item.get("pClosing")

                    if last_price is None and closing_price is None:
                        continue

                    records.append({
                        "ins_code": fund_obj.ins_code,
                        "last_price": last_price,
                        "closing_price": closing_price,
                        "observed_at": observed_at,
                    })

                if records:
                    stmt = pg_insert(
                        ETFMarketHistory
                    ).values(records)

                    stmt = stmt.on_conflict_do_update(
                        index_elements=[
                            "ins_code",
                            "observed_at",
                        ],
                        set_={
                            "last_price": stmt.excluded.last_price,
                            "closing_price": stmt.excluded.closing_price,
                        },
                    )

                    db.execute(stmt)
                    db.commit()

                    logger.info(
                        "Backfilled %s ETF price observations for %s",
                        len(records),
                        fund_obj.ins_code,
                    )
        
    except Exception as e:
        db.rollback()
        logger.error(f"Error backfilling funds: {e}")
    finally:
        db.close()
