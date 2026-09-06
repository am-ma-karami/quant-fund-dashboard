from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from database import Base

class Fund(Base):
    __tablename__ = "funds"
    
    reg_no = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=True)
    fund_type = Column(Integer, default=6)
    net_asset = Column(Float, nullable=True)
    nav_stat = Column(Float, nullable=True)
    last_updated = Column(DateTime, default=datetime.utcnow)
    
    # ارتباط یک به چند با تاریخچه
    histories = relationship("FundHistory", back_populates="fund", order_by="desc(FundHistory.recorded_at)")

class FundHistory(Base):
    __tablename__ = "fund_histories"
    
    id = Column(Integer, primary_key=True, index=True)
    fund_reg_no = Column(Integer, ForeignKey("funds.reg_no"), index=True)
    nav_stat = Column(Float, nullable=True)
    net_asset = Column(Float, nullable=True)
    recorded_at = Column(DateTime, default=datetime.utcnow, index=True)
    
    fund = relationship("Fund", back_populates="histories")