from sqlalchemy.orm import Session
from core.models import Fund, FundHistory, ETFMarket, ETFMarketHistory
from datetime import datetime

class FundRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_fund_by_reg_no(self, reg_no: int):
        return self.db.query(Fund).filter(Fund.reg_no == reg_no).first()

    def get_funds_by_type(self, type_id: int):
        return self.db.query(Fund).filter(Fund.fund_type == type_id).order_by(Fund.net_asset.desc()).all()

    def get_top_funds_by_return(self, limit: int = 10):
        return self.db.query(Fund).filter(Fund.fund_type == 6, Fund.day30_return != None)\
                      .order_by(Fund.day30_return.desc()).limit(limit).all()

    def get_fund_history(self, reg_no: int, limit: int = 60):
        return self.db.query(FundHistory).filter(FundHistory.fund_reg_no == reg_no)\
                      .order_by(FundHistory.recorded_at.asc()).limit(limit).all()

    def upsert_fund(self, reg_no: int, name: str, fund_type: int, clean_data: dict):
        """بروزرسانی یا ساخت صندوق جدید (Upsert)"""
        fund = self.get_fund_by_reg_no(reg_no)
        if not fund:
            fund = Fund(reg_no=reg_no, name=name, fund_type=fund_type)
            self.db.add(fund)
            
        fund.nav_stat = clean_data['nav_stat']
        fund.nav_sub = clean_data['nav_sub']
        fund.nav_red = clean_data['nav_red']
        fund.net_asset = clean_data['net_asset']
        fund.units = clean_data['units']
        fund.manager = clean_data['manager']
        fund.day30_return = clean_data['day30_return']
        fund.day90_return = clean_data['day90_return']
        fund.day365_return = clean_data['day365_return']
        fund.portfolio_stock = clean_data['portfolio_stock']
        fund.portfolio_bond = clean_data['portfolio_bond']
        fund.portfolio_deposit = clean_data['portfolio_deposit']
        fund.fund_type = fund_type
        fund.last_updated = datetime.utcnow()
        return fund

    def add_fund_history(self, reg_no: int, nav_stat: float, net_asset: float):
        history = FundHistory(fund_reg_no=reg_no, nav_stat=nav_stat, net_asset=net_asset)
        self.db.add(history)


class ETFRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_all_etfs(self):
        return self.db.query(ETFMarket).order_by(ETFMarket.total_trades.desc()).all()

    def upsert_etf_market(self, ins_code: str, symbol: str, name: str, data: dict):
        etf = self.db.query(ETFMarket).filter(ETFMarket.ins_code == ins_code).first()
        if not etf:
            etf = ETFMarket(ins_code=ins_code, symbol=symbol, name=name)
            self.db.add(etf)
            
        etf.last_price = data['last_price']
        etf.closing_price = data['closing_price']
        etf.price_change = data['price_change']
        etf.total_trades = data['total_trades']
        etf.last_updated = datetime.utcnow()
        return etf

    def add_etf_history(self, ins_code: str, last_price: float, closing_price: float):
        history = ETFMarketHistory(ins_code=ins_code, last_price=last_price, closing_price=closing_price)
        self.db.add(history)