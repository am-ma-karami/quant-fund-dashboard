"""History backfill: تکمیل تاریخچه NAV صندوق‌ها و قیمت ETF ها از TSETMC.

کارگر این ماژول را هر ۱۰ ثانیه اجرا می‌کند. هر صندوق حداکثر هر
STALE_SOURCE_RETRY_HOURS ساعت یک‌بار امتحان می‌شود (در جدول
history_backfill_state ثبت می‌شود) تا صندوق‌هایی که در منبع اصلی
کمتر از ۹۰ رکورد دارند، در یک حلقه بی‌نهایت دانلود نشوند.
"""
import logging
from datetime import timedelta

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert as pg_insert

from core.database import SessionLocal
from core.models import (
    Fund,
    FundHistory,
    ETFMarketHistory,
    HistoryBackfillState,
)
from core.repositories import FundRepository, iran_time
from services.providers import TSETMCProvider, parse_tsetmc_date


logger = logging.getLogger(__name__)

provider = TSETMCProvider()

STALE_SOURCE_RETRY_HOURS = 6
BACKFILL_TARGET_RECORDS = 90
BACKFILL_BATCH_SIZE = 10
ETF_HISTORY_DAYS = 90
# پنجره‌ای که در آن یک صندوق «محدود به منبع» (تاریخچه منبع کمتر از ۹۰ رکورد)
# در داشبورد «کامل» شمرده می‌شود. از فاصله تلاش مجدد (۶ ساعت) بزرگ‌تر است تا
# بین دو چرخه بررسی، عدد جلو و عقب نپرد.
SOURCE_COMPLETE_MAX_AGE_HOURS = 24


def _funds_needing_backfill(db, limit: int) -> list[Fund]:
    """صندوق‌هایی که تاریخچه‌شان کمتر از حد نصاب است و اخیراً چک نشده‌اند."""
    history_counts = (
        db.query(
            FundHistory.fund_reg_no,
            func.count(FundHistory.id).label("history_count"),
        )
        .group_by(FundHistory.fund_reg_no)
        .subquery()
    )

    retry_cutoff = iran_time() - timedelta(hours=STALE_SOURCE_RETRY_HOURS)

    return (
        db.query(Fund)
        .outerjoin(
            history_counts,
            Fund.reg_no == history_counts.c.fund_reg_no,
        )
        .outerjoin(
            HistoryBackfillState,
            Fund.reg_no == HistoryBackfillState.fund_reg_no,
        )
        .filter(
            func.coalesce(history_counts.c.history_count, 0)
            < BACKFILL_TARGET_RECORDS,
            (
                HistoryBackfillState.checked_at.is_(None)
                | (HistoryBackfillState.checked_at < retry_cutoff)
            ),
        )
        .order_by(func.coalesce(history_counts.c.history_count, 0).asc())
        .limit(limit)
        .all()
    )


def _mark_checked(db, reg_no: int, source_count: int | None = None):
    """ثبت زمان آخرین تلاش backfill تا صندوق بی‌نهایت دانلود نشود.

    ``source_count`` تعداد رکوردهای معتبری است که منبع در این تلاش برگرداند؛
    فقط در تلاش موفق ثبت می‌شود — None یعنی مقدار قبلی دست نمی‌خورد (شکست
    نباید شواهد یک تلاش موفق قبلی را پاک کند).
    """
    try:
        state = db.get(HistoryBackfillState, reg_no)
        if state is not None:
            state.checked_at = iran_time()
            if source_count is not None:
                state.source_count = source_count
        else:
            db.add(
                HistoryBackfillState(
                    fund_reg_no=reg_no,
                    checked_at=iran_time(),
                    source_count=source_count,
                )
            )
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Failed to record backfill state for fund %s", reg_no)


def _backfill_etf_history(db, fund: Fund):
    """تکمیل تاریخچه قیمت ETF مرتبط با صندوق."""
    etf_history = provider.fetch_etf_history(fund.ins_code, limit=0)

    cutoff = iran_time() - timedelta(days=ETF_HISTORY_DAYS)

    records = []

    for item in etf_history:
        observed_at = parse_tsetmc_date(item.get("dEven"))

        if observed_at is None or observed_at < cutoff:
            continue

        last_price = item.get("pDrCotVal")
        closing_price = item.get("pClosing")

        if last_price is None and closing_price is None:
            continue

        records.append({
            "ins_code": fund.ins_code,
            "last_price": last_price,
            "closing_price": closing_price,
            "observed_at": observed_at,
        })

    if not records:
        return

    stmt = pg_insert(ETFMarketHistory).values(records)
    stmt = stmt.on_conflict_do_update(
        index_elements=["ins_code", "observed_at"],
        set_={
            "last_price": stmt.excluded.last_price,
            "closing_price": stmt.excluded.closing_price,
        },
    )

    db.execute(stmt)

    logger.info(
        "Backfilled %s ETF price observations for %s",
        len(records),
        fund.ins_code,
    )


def _backfill_fund(db, repo: FundRepository, fund: Fund) -> int | None:
    """دانلود و ذخیره کامل‌ترین تاریخچه موجود برای یک صندوق.

    تعداد رکوردهای معتبر منبع را برمی‌گرداند (۰ یعنی پاسخ خالی معتبر)؛
    None یعنی دریافت شکست خورد و چیزی قابل استناد نیست.
    """
    reg_no = fund.reg_no
    logger.info("Backfilling history for Fund %s...", reg_no)

    history_data = provider.fetch_fund_history_detail(reg_no)

    if history_data is None:
        logger.warning("History fetch failed for Fund %s", reg_no)
        return None

    parsed_history = []
    for item in history_data:
        observed_at = parse_tsetmc_date(item.get("recordDate"))
        if observed_at is None:
            continue
        parsed_history.append((observed_at, item))

    parsed_history.sort(key=lambda entry: entry[0], reverse=True)

    recent = parsed_history[:BACKFILL_TARGET_RECORDS]
    for observed_at, item in recent:
        repo.upsert_fund_history(
            reg_no=reg_no,
            nav_stat=item.get("navStat"),
            nav_sub=item.get("navSub"),
            nav_red=item.get("navRed"),
            net_asset=item.get("netAsset"),
            units=item.get("units"),
            observed_at=observed_at,
        )

    db.commit()

    logger.info(
        "Successfully backfilled %s history records for Fund %s.",
        len(recent),
        reg_no,
    )

    if fund.is_etf and fund.ins_code:
        try:
            _backfill_etf_history(db, fund)
            db.commit()
        except Exception:
            db.rollback()
            logger.exception(
                "ETF history backfill failed for %s",
                fund.ins_code,
            )

    return len(recent)


def backfill_single_fund():
    """
    پیدا کردن خودکار چند صندوق که تاریخچه ناقص دارد (کمتر از ۹۰ رکورد)
    و تکمیل دیتای آن‌ها از طریق API بورس.
    """
    db = SessionLocal()
    fund_repo = FundRepository(db)

    try:
        funds_to_backfill = _funds_needing_backfill(db, BACKFILL_BATCH_SIZE)

        if not funds_to_backfill:
            logger.info(
                "All funds have complete %s-record history. Nothing to backfill.",
                BACKFILL_TARGET_RECORDS,
            )
            return

        for fund in funds_to_backfill:
            reg_no = fund.reg_no

            source_count = None
            try:
                source_count = _backfill_fund(db, fund_repo, fund)
            except Exception:
                db.rollback()
                logger.exception("Error backfilling Fund %s", reg_no)

            _mark_checked(db, reg_no, source_count=source_count)

    finally:
        db.close()
