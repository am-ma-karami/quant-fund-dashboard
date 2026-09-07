from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from core.database import Base

class Fund(Base):
    __tablename__ = "funds"
    
    reg_no = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=True)
    fund_type = Column(Integer, default=6)
    
    # اطلاعات قیمتی و دارایی
    net_asset = Column(Float, nullable=True)
    nav_stat = Column(Float, nullable=True)  # NAV آماری
    nav_sub = Column(Float, nullable=True)   # NAV صدور
    nav_red = Column(Float, nullable=True)   # NAV ابطال
    units = Column(Float, nullable=True)     # تعداد واحدهای سرمایه‌گذاری
    
    # اطلاعات هویتی
    manager = Column(String, nullable=True)  # مدیر صندوق
    
    # بازدهی‌ها (Returns)
    day30_return = Column(Float, nullable=True)
    day90_return = Column(Float, nullable=True)
    day365_return = Column(Float, nullable=True)
    
    # ترکیب دارایی‌ها (Portfolio)
    portfolio_stock = Column(Float, nullable=True)   # درصد سهام
    portfolio_bond = Column(Float, nullable=True)    # درصد اوراق
    portfolio_deposit = Column(Float, nullable=True) # درصد سپرده/نقد
    
    last_updated = Column(DateTime, default=datetime.utcnow)
    
    histories = relationship("FundHistory", back_populates="fund", order_by="desc(FundHistory.recorded_at)")

class FundHistory(Base):
    __tablename__ = "fund_histories"
    
    id = Column(Integer, primary_key=True, index=True)
    fund_reg_no = Column(Integer, ForeignKey("funds.reg_no"), index=True)
    nav_stat = Column(Float, nullable=True)
    net_asset = Column(Float, nullable=True)
    recorded_at = Column(DateTime, default=datetime.utcnow, index=True)
    
    fund = relationship("Fund", back_populates="histories")


class ETFMarket(Base):
    """ذخیره وضعیت لحظه‌ای معاملات روی تابلوی ETFها"""
    __tablename__ = "etf_market"
    
    ins_code = Column(String, primary_key=True, index=True)
    symbol = Column(String, index=True)      # نماد (مثلا: دارا یکم)
    name = Column(String)                    # نام کامل
    
    last_price = Column(Float, nullable=True)     # pDrCotVal (آخرین معامله)
    closing_price = Column(Float, nullable=True)  # pClosing (قیمت پایانی)
    price_change = Column(Float, nullable=True)   # تغییر قیمت
    
    total_trades = Column(Float, nullable=True)   # zTotTran (تعداد معاملات)
    last_updated = Column(DateTime, default=datetime.utcnow)
    
    histories = relationship("ETFMarketHistory", back_populates="etf", order_by="desc(ETFMarketHistory.recorded_at)")

class ETFMarketHistory(Base):
    """تاریخچه دقیقه به دقیقه قیمت روی تابلوی ETFها"""
    __tablename__ = "etf_market_histories"
    
    id = Column(Integer, primary_key=True, index=True)
    ins_code = Column(String, ForeignKey("etf_market.ins_code"), index=True)
    
    last_price = Column(Float, nullable=True)
    closing_price = Column(Float, nullable=True)
    recorded_at = Column(DateTime, default=datetime.utcnow, index=True)
    
    etf = relationship("ETFMarket", back_populates="histories")