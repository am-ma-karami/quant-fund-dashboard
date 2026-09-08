from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey
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
    day30_return = Column(Float, nullable=True)
    day90_return = Column(Float, nullable=True)
    day365_return = Column(Float, nullable=True)
    portfolio_stock = Column(Float, nullable=True)
    portfolio_bond = Column(Float, nullable=True)
    portfolio_deposit = Column(Float, nullable=True)
    
    last_updated = Column(DateTime, default=iran_time)
    histories = relationship("FundHistory", back_populates="fund", order_by="desc(FundHistory.recorded_at)")

class FundHistory(Base):
    __tablename__ = "fund_histories"
    id = Column(Integer, primary_key=True, index=True)
    fund_reg_no = Column(Integer, ForeignKey("funds.reg_no"), index=True)
    nav_stat = Column(Float, nullable=True)
    net_asset = Column(Float, nullable=True)
    recorded_at = Column(DateTime, default=iran_time, index=True) 
    fund = relationship("Fund", back_populates="histories")

class ETFMarket(Base):
    __tablename__ = "etf_market"
    ins_code = Column(String, primary_key=True, index=True)
    symbol = Column(String, index=True)
    name = Column(String)
    last_price = Column(Float, nullable=True)
    closing_price = Column(Float, nullable=True)
    price_change = Column(Float, nullable=True)
    total_trades = Column(Float, nullable=True)
    last_updated = Column(DateTime, default=iran_time)
    histories = relationship("ETFMarketHistory", back_populates="etf", order_by="desc(ETFMarketHistory.recorded_at)")

class ETFMarketHistory(Base):
    __tablename__ = "etf_market_histories"
    id = Column(Integer, primary_key=True, index=True)
    ins_code = Column(String, ForeignKey("etf_market.ins_code"), index=True)
    last_price = Column(Float, nullable=True)
    closing_price = Column(Float, nullable=True)
    recorded_at = Column(DateTime, default=iran_time, index=True) 
    etf = relationship("ETFMarket", back_populates="histories")