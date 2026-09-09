import logging
from datetime import timedelta

from dateutil import parser

from core.database import SessionLocal
from core.repositories import FundRepository, iran_time
from services.providers import TSETMCProvider


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


def backfill_single_fund(
    history_days: int = HISTORY_DAYS,
    initial_records: int = INITIAL_HISTORY_RECORDS,
):
    """
    Backfill one fund per run. Every fund first receives a few recent records;
    only then are all funds completed up to the configured history window.
    """
    db = SessionLocal()
    repo = FundRepository(db)

    try:
        cutoff = iran_time() - timedelta(days=history_days)
        fund, phase = repo.get_next_history_backfill_fund(
            initial_records=initial_records,
            target_records=history_days,
        )
        completed, total = repo.get_history_backfill_progress(history_days, since=cutoff)
        covered, _ = repo.get_history_backfill_progress(1, since=cutoff)
        if not fund:
            logger.info(
                "History backfill complete: %s/%s funds have %s recent records",
                completed, total, history_days,
            )
            return False

        record_limit = initial_records if phase == "initial" else history_days
        logger.info(
            "History backfill [%s]: fund %s (historical coverage %s/%s; 30-day completion %s/%s; %s records now)",
            phase, fund.reg_no, covered, total, completed, total, repo.get_history_count(fund.reg_no, since=cutoff),
        )

        history_data = provider.fetch_fund_history_detail(
            fund.reg_no
        )

        history_records, source_mode = _history_records_for_backfill(
            history_data, history_days, record_limit
        )
        if not history_records:
            repo.mark_history_source_stale(fund.reg_no)
            db.commit()
            logger.warning(
                "Fund %s has no history in the last %s days; retry deferred for %s hours",
                fund.reg_no, history_days, STALE_SOURCE_RETRY_HOURS,
            )
            return True

        count = 0
        for observed_at, item in history_records:

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

        if count == 0 and repo.get_history_count(fund.reg_no, since=cutoff) < record_limit:
            repo.mark_history_source_stale(fund.reg_no)
            db.commit()
            logger.warning(
                "Fund %s did not provide additional recent observations; retry deferred for %s hours",
                fund.reg_no, STALE_SOURCE_RETRY_HOURS,
            )

        completed, total = repo.get_history_backfill_progress(history_days, since=cutoff)
        covered, _ = repo.get_history_backfill_progress(1, since=cutoff)
        logger.info(
            "History backfill [%s/%s] finished for fund %s: +%s records; recent coverage %s/%s; 30-day completion %s/%s",
            phase, source_mode, fund.reg_no, count, covered, total, completed, total,
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
