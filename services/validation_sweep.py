"""جاروب دوره‌ای اعتبارسنجی (Validation Sweep).

در حالی که مسیر زنده فقط اعتبارسنجی سبک inline انجام می‌دهد (چون هر دقیقه
اجرا می‌شود)، این جاب هر ۱۵ دقیقه یک‌بار سری‌های تاریخی را کامل جاروب
می‌کند: outlier آماری بازده‌ها، شکاف‌های زمانی بزرگ و کهنگی داده.
"""
import logging
from datetime import timedelta

from core.database import SessionLocal
from core.models import Fund, FundHistory
from core.repositories import DataQualityRepository, iran_time
from services.validation import sweep_fund_history


logger = logging.getLogger(__name__)

SWEEP_WINDOW_DAYS = 90


def run_validation_sweep():
    """جاروب تاریخچه همه صندوق‌ها و ثبت تخلف‌های شناسایی‌شده."""
    db = SessionLocal()
    repo = DataQualityRepository(db)

    try:
        cutoff = iran_time() - timedelta(days=SWEEP_WINDOW_DAYS)

        rows = (
            db.query(
                FundHistory.fund_reg_no,
                FundHistory.nav_stat,
                FundHistory.observed_at,
                Fund.fund_type,
            )
            .join(Fund, FundHistory.fund_reg_no == Fund.reg_no)
            .filter(FundHistory.observed_at >= cutoff)
            .order_by(FundHistory.fund_reg_no, FundHistory.observed_at)
            .all()
        )

        history_by_fund = {}
        for reg_no, nav, observed_at, fund_type in rows:
            history_by_fund.setdefault(reg_no, {"navs": [], "dates": [], "fund_type": fund_type})
            history_by_fund[reg_no]["navs"].append(nav)
            history_by_fund[reg_no]["dates"].append(observed_at)

        issues = []
        for reg_no, data in history_by_fund.items():
            issues.extend(
                sweep_fund_history(
                    reg_no,
                    data["navs"],
                    data["dates"],
                    fund_type=data["fund_type"],
                )
            )

        recorded = repo.record_issues(issues)
        db.commit()

        logger.info(
            "Validation sweep completed: %s issues recorded across %s funds",
            recorded,
            len(history_by_fund),
        )

    except Exception:
        db.rollback()
        logger.exception("Validation sweep failed")

    finally:
        db.close()
