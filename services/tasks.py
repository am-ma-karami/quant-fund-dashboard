import logging
from datetime import datetime

from core.database import SessionLocal
from core.models import Fund, FundHistory, ETFMarket, ETFMarketHistory
from services.tsetmc_client import fetch_funds_by_type, fetch_live_etf_prices
from services.preprocessing import clean_fund_data

logger = logging.getLogger(__name__)

# لیست تمام کدهای انواع صندوق‌ها بر اساس مستندات
FUND_TYPES = [4, 5, 6, 7, 11, 12, 13, 14, 16, 17]

def update_funds_data():
    """این تابع هر یک دقیقه توسط Scheduler اجرا می‌شود"""
    logger.info("Starting data collection task for ALL categories...")
    
    db = SessionLocal()
    total_updated = 0
    
    try:
        
        for f_type in FUND_TYPES:

            funds_data = fetch_funds_by_type(f_type)
            if not funds_data:
                continue

            for item in funds_data:
                # عبور دیتای خام از فیلتر پیش‌پردازش
                clean_item = clean_fund_data(item)
                
                reg_no = clean_item['reg_no']
                if reg_no == 0:
                    continue
                    
                # ذخیره یا آپدیت اطلاعات اصلی صندوق
                fund = db.query(Fund).filter(Fund.reg_no == reg_no).first()
                if not fund:
                    fund = Fund(reg_no=reg_no, name=clean_item['name'], fund_type=f_type)
                    db.add(fund)
                
                # مقداردهی با دیتای تمیز و اعتبارسنجی شده
                fund.nav_stat = clean_item['nav_stat']
                fund.nav_sub = clean_item['nav_sub']
                fund.nav_red = clean_item['nav_red']
                fund.net_asset = clean_item['net_asset']
                fund.units = clean_item['units']
                
                fund.manager = clean_item['manager']
                fund.day30_return = clean_item['day30_return']
                fund.day90_return = clean_item['day90_return']
                fund.day365_return = clean_item['day365_return']
                
                fund.portfolio_stock = clean_item['portfolio_stock']
                fund.portfolio_bond = clean_item['portfolio_bond']
                fund.portfolio_deposit = clean_item['portfolio_deposit']
                
                fund.fund_type = f_type
                fund.last_updated = datetime.utcnow()
                
                # رکورد تاریخچه برای رسم نمودار
                history_record = FundHistory(
                    fund_reg_no=reg_no,
                    nav_stat=clean_item['nav_stat'],
                    net_asset=clean_item['net_asset']
                )
                db.add(history_record)
                total_updated += 1
                
        db.commit()
        logger.info(f"Successfully updated {total_updated} funds across {len(FUND_TYPES)} categories.")
    except Exception as e:
        db.rollback()
        logger.error(f"Database error during update: {e}")
    finally:
        db.close()


def update_etf_market_data():
    """تسک دریافت قیمت‌های تابلوی ETFها"""
    logger.info("Starting live ETF market data collection...")
    db = SessionLocal()
    try:
        etf_data = fetch_live_etf_prices()
        if not etf_data:
            return

        for item in etf_data:
            ins_code = item.get("insCode")
            if not ins_code:
                continue
            
            # استخراج اطلاعات از ساب‌آبجکت instrument
            instrument = item.get("instrument", {})
            symbol = instrument.get("lVal18AFC", "نامشخص")
            name = instrument.get("lVal30", "نامشخص")
            
            last_price = item.get("pDrCotVal")
            closing_price = item.get("pClosing")
            price_change = item.get("priceChange")
            total_trades = item.get("zTotTran")
            
            # ذخیره یا آپدیت
            etf = db.query(ETFMarket).filter(ETFMarket.ins_code == ins_code).first()
            if not etf:
                etf = ETFMarket(ins_code=ins_code, symbol=symbol, name=name)
                db.add(etf)
            
            etf.last_price = last_price
            etf.closing_price = closing_price
            etf.price_change = price_change
            etf.total_trades = total_trades
            etf.last_updated = datetime.utcnow()
            
            # رکورد تاریخچه قیمتی برای نمودار
            history = ETFMarketHistory(
                ins_code=ins_code,
                last_price=last_price,
                closing_price=closing_price
            )
            db.add(history)
            
        db.commit()
        logger.info(f"Successfully updated {len(etf_data)} ETF market prices.")
    except Exception as e:
        db.rollback()
        logger.error(f"Error in ETF market update: {e}")
    finally:
        db.close()