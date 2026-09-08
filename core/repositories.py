from sqlalchemy.orm import Session
from core.models import Fund, FundHistory, ETFMarket, ETFMarketHistory
from datetime import datetime

from zoneinfo import ZoneInfo

def iran_time():
    return datetime.now(ZoneInfo("Asia/Tehran")).replace(tzinfo=None)

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
                      .order_by(FundHistory.observed_at.asc()).limit(limit).all()

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
        fund.day1_return = clean_data['day1_return']
        fund.day7_return = clean_data['day7_return']
        fund.day180_return = clean_data['day180_return']
        fund.portfolio_stock = clean_data['portfolio_stock']
        fund.portfolio_bond = clean_data['portfolio_bond']
        fund.portfolio_deposit = clean_data['portfolio_deposit']
        fund.fund_type = fund_type
        fund.last_updated = iran_time()
        return fund

    def add_fund_history(self, reg_no: int, nav_stat: float, net_asset: float,observed_at=None):
        history = FundHistory(fund_reg_no=reg_no, nav_stat=nav_stat, net_asset=net_asset, بobserved_at=observed_at or iran_time())        
        self.db.add(history)

    def get_heatmap_data(self, limit: int = 50):
        """دریافت دیتای صندوق‌های بزرگ برای نقشه حرارتی"""
        # فقط صندوق‌هایی که دیتای Asset و Return دارند را می‌گیریم
        return self.db.query(Fund).filter(
            Fund.net_asset > 0,
            Fund.day30_return != None
        ).order_by(Fund.net_asset.desc()).limit(limit).all()

    def get_all_funds_for_screener(self):
        """دریافت تمام صندوق‌ها برای صفحه فیلترنویسی"""
        return self.db.query(Fund).filter(Fund.net_asset > 0).all()

    def get_latest_observation_time(self, reg_no: int):
        """گرفتن آخرین زمان دیتای ثبت شده برای یک صندوق"""
        latest = self.db.query(FundHistory).filter(FundHistory.fund_reg_no == reg_no)\
                        .order_by(FundHistory.observed_at.desc()).first()
        return latest.observed_at if latest else None

    def upsert_fund_history(self, reg_no: int, nav_stat: float, net_asset: float, observed_at: datetime):
        """منطق UPSERT: اگر بود آپدیت کن، اگر نبود بساز"""
        history = self.db.query(FundHistory).filter(
            FundHistory.fund_reg_no == reg_no,
            FundHistory.observed_at == observed_at
        ).first()
        
        if history:
            # Correction: اگر دیتا در بورس اصلاح شده بود، ما هم آپدیت می‌کنیم
            history.nav_stat = nav_stat
            history.net_asset = net_asset
        else:
            # Insert
            history = FundHistory(
                fund_reg_no=reg_no,
                nav_stat=nav_stat,
                net_asset=net_asset,
                observed_at=observed_at
            )
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
        etf.last_updated = iran_time()
        return etf

    def add_etf_history(self, ins_code: str, last_price: float, closing_price: float, observed_at):
        history = ETFMarketHistory(ins_code=ins_code, last_price=last_price, closing_price=closing_price, observed_at=observed_at or iran_time())
        self.db.add(history)

    def get_etf_by_ins_code(self, ins_code: str):
        return self.db.query(ETFMarket).filter(ETFMarket.ins_code == ins_code).first()

    def get_etf_history(self, ins_code: str, limit: int = 60):
        return self.db.query(ETFMarketHistory).filter(ETFMarketHistory.ins_code == ins_code).order_by(ETFMarketHistory.observed_at.asc()).limit(limit).all()


    def get_market_pulse(self):
        """
        محاسبه شاخص‌های کلان بازار (Market Pulse) بر اساس تابلوی لایو ETFها
        """
        etfs = self.db.query(ETFMarket).all()
        total = len(etfs)
        
        if total == 0:
            return {"total": 0, "positive": 0, "negative": 0, "unchanged": 0, 
                    "total_trades": 0, "breadth": 0, "up_volume_ratio": 0}

        positive = sum(1 for e in etfs if (e.price_change or 0) > 0)
        negative = sum(1 for e in etfs if (e.price_change or 0) < 0)
        unchanged = total - positive - negative
        
        # مجموع کل معاملات انجام شده در بازار
        total_trades = sum((e.total_trades or 0) for e in etfs)
        
        # معاملاتی که روی صندوق‌های مثبت انجام شده (Up Volume Proxy)
        up_trades = sum((e.total_trades or 0) for e in etfs if (e.price_change or 0) > 0)
        
        # محاسبه Breadth (درصد صندوق‌های مثبت نسبت به کل)
        breadth = (positive / total) * 100
        
        # محاسبه Up Volume Ratio
        up_volume_ratio = (up_trades / total_trades) * 100 if total_trades > 0 else 0
        
        return {
            "total": total,
            "positive": positive,
            "negative": negative,
            "unchanged": unchanged,
            "total_trades": total_trades,
            "breadth": round(breadth, 1),
            "up_volume_ratio": round(up_volume_ratio, 1)
        }