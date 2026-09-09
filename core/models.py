from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from datetime import datetime
from zoneinfo import ZoneInfo
from core.database import Base


def iran_time():
    """تولید ساعت فعلی به وقت تهران (برای جلوگیری از ارور دیتابیس، بدون تایم‌زون ذخیره می‌شود)"""
    return datetime.now(ZoneInfo("Asia/Tehran")).replace(tzinfo=None)


class Fund(Base):
    __tablename__ = "funds"

    reg_no = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=True)
    fund_type = Column(Integer, default=6)

    net_asset = Column(Float, nullable=True)
    nav_stat = Column(Float, nullable=True)
    nav_sub = Column(Float, nullable=True)
    nav_red = Column(Float, nullable=True)
    units = Column(Float, nullable=True)
    manager = Column(String, nullable=True)
    day1_return = Column(Float, nullable=True)
    day7_return = Column(Float, nullable=True)
    day180_return = Column(Float, nullable=True)
    day30_return = Column(Float, nullable=True)
    day90_return = Column(Float, nullable=True)
    day365_return = Column(Float, nullable=True)
    portfolio_stock = Column(Float, nullable=True)
    portfolio_bond = Column(Float, nullable=True)
    portfolio_deposit = Column(Float, nullable=True)

    volatility = Column(Float, nullable=True)
    sharpe_ratio = Column(Float, nullable=True)
    max_drawdown = Column(Float, nullable=True)

    last_updated = Column(DateTime, default=iran_time)
    histories = relationship("FundHistory", back_populates="fund", order_by="desc(FundHistory.observed_at)")

    @property
    def risk_profile(self):
        """محاسبه سطح ریسک بر اساس ترکیب دارایی (Quant Approach)"""
        stock = self.portfolio_stock or 0
        bond = self.portfolio_bond or 0

        if stock >= 65:
            return {"level": "High (پرریسک)", "color": "danger", "score": 8}
        elif stock >= 30:
            return {"level": "Medium (متوسط)", "color": "warning", "score": 5}
        elif bond >= 70:
            return {"level": "Low (کم‌ریسک)", "color": "success", "score": 2}
        else:
            return {"level": "Mixed (مختلط)", "color": "info", "score": 4}


class FundHistory(Base):
    __tablename__ = "fund_histories"

    id = Column(Integer, primary_key=True, index=True)
    fund_reg_no = Column(Integer, ForeignKey("funds.reg_no"), index=True)

    nav_stat = Column(Float, nullable=True)
    nav_sub = Column(Float, nullable=True)
    nav_red = Column(Float, nullable=True)
    net_asset = Column(Float, nullable=True)
    units = Column(Float, nullable=True)

    # زمانی که این دیتا در بورس ثبت شده (مثلا پایان روز کاری)
    observed_at = Column(DateTime, nullable=False, index=True)
    # زمانی که کرون‌جاب ما این دیتا را در دیتابیس خودمان ثبت کرد
    created_at = Column(DateTime, default=iran_time)

    fund = relationship("Fund", back_populates="histories")

    # جلوگیری از دیتای تکراری: برای هر صندوق در یک زمان مشخص، فقط یک رکورد
    __table_args__ = (
        UniqueConstraint('fund_reg_no', 'observed_at', name='uix_fund_observation'),
    )


class HistoryBackfillState(Base):
    """Records temporary source-data gaps so one stale fund cannot block the queue."""
    __tablename__ = "history_backfill_state"

    fund_reg_no = Column(Integer, ForeignKey("funds.reg_no"), primary_key=True)
    checked_at = Column(DateTime, nullable=False, default=iran_time, index=True)


class ETFMarket(Base):
    __tablename__ = "etf_market"

    ins_code = Column(String, primary_key=True, index=True)
    symbol = Column(String, index=True)
    name = Column(String)

    last_price = Column(Float, nullable=True)
    closing_price = Column(Float, nullable=True)
    price_change = Column(Float, nullable=True)

    total_trades = Column(Integer, nullable=True)
    total_volume = Column(Float, nullable=True)
    total_value = Column(Float, nullable=True)

    price_min = Column(Float, nullable=True)
    price_max = Column(Float, nullable=True)
    price_first = Column(Float, nullable=True)
    price_yesterday = Column(Float, nullable=True)

    nav = Column(Float, nullable=True)
    nav_red = Column(Float, nullable=True)
    nav_sub = Column(Float, nullable=True)
    premium_discount = Column(Float, nullable=True)

    volatility = Column(Float, nullable=True)
    sharpe_ratio = Column(Float, nullable=True)
    max_drawdown = Column(Float, nullable=True)

    last_updated = Column(DateTime, default=iran_time)
    histories = relationship(
        "ETFMarketHistory",
        back_populates="etf",
        order_by="desc(ETFMarketHistory.observed_at)"
    )


class ETFMarketHistory(Base):
    __tablename__ = "etf_market_histories"

    id = Column(Integer, primary_key=True, index=True)

    ins_code = Column(
        String,
        ForeignKey("etf_market.ins_code"),
        index=True,
        nullable=False
    )

    last_price = Column(Float, nullable=True)
    closing_price = Column(Float, nullable=True)
    price_change = Column(Float, nullable=True)

    total_trades = Column(Integer, nullable=True)
    total_volume = Column(Float, nullable=True)
    total_value = Column(Float, nullable=True)

    price_min = Column(Float, nullable=True)
    price_max = Column(Float, nullable=True)
    price_first = Column(Float, nullable=True)
    price_yesterday = Column(Float, nullable=True)

    nav = Column(Float, nullable=True)
    nav_red = Column(Float, nullable=True)
    nav_sub = Column(Float, nullable=True)
    premium_discount = Column(Float, nullable=True)

    observed_at = Column(DateTime, nullable=False, index=True)
    created_at = Column(DateTime, default=iran_time)

    etf = relationship(
        "ETFMarket",
        back_populates="histories"
    )

    __table_args__ = (
        UniqueConstraint(
            "ins_code",
            "observed_at",
            name="uix_etf_observation"
        ),
    )


class SyncStatus(Base):
    __tablename__ = "sync_status"

    id = Column(Integer, primary_key=True)
    job_name = Column(String, unique=True, nullable=False)

    status = Column(String, nullable=False)

    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)

    expected_count = Column(Integer, default=0)
    received_count = Column(Integer, default=0)
    valid_count = Column(Integer, default=0)

    updated_count = Column(Integer, default=0)
    failed_count = Column(Integer, default=0)

    duration_ms = Column(Integer, nullable=True)
    last_success_at = Column(DateTime, nullable=True)

    provider = Column(String, default="TSETMC")

    error_message = Column(String, nullable=True)
