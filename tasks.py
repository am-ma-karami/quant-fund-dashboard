import logging
from datetime import datetime
from database import SessionLocal
from models import Fund, FundHistory
from tsetmc_client import fetch_stock_funds

logger = logging.getLogger(__name__)

def update_funds_data():
    """این تابع هر یک دقیقه توسط Scheduler اجرا می‌شود"""
    logger.info("Starting data collection task...")
    funds_data = fetch_stock_funds()
    
    if not funds_data:
        logger.warning("No data received from API.")
        return

    db = SessionLocal()
    try:
        for item in funds_data:
            reg_no = int(item.get("regNo", 0))
            if reg_no == 0:
                continue
                
            name = item.get("mfName", "نامشخص")
            nav_stat = item.get("navStat")
            net_asset = item.get("netAsset")
            
            # ۱. ذخیره یا آپدیت اطلاعات اصلی صندوق
            fund = db.query(Fund).filter(Fund.reg_no == reg_no).first()
            if not fund:
                fund = Fund(reg_no=reg_no, name=name)
                db.add(fund)
            
            fund.nav_stat = nav_stat
            fund.net_asset = net_asset
            fund.last_updated = datetime.utcnow()
            
            # ۲. اضافه کردن یک رکورد به تاریخچه برای رسم نمودار و بررسی لایو
            history_record = FundHistory(
                fund_reg_no=reg_no,
                nav_stat=nav_stat,
                net_asset=net_asset
            )
            db.add(history_record)
            
        db.commit()
        logger.info(f"Successfully updated {len(funds_data)} funds.")
    except Exception as e:
        db.rollback()
        logger.error(f"Database error during update: {e}")
    finally:
        db.close()