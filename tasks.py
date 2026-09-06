import logging
from datetime import datetime
from database import SessionLocal
from models import Fund, FundHistory
from tsetmc_client import fetch_funds_by_type

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
                reg_no = int(item.get("regNo", 0))
                if reg_no == 0:
                    continue
                    
                name = item.get("mfName", "نامشخص")
                nav_stat = item.get("navStat")
                net_asset = item.get("netAsset")
                
                # ذخیره یا آپدیت اطلاعات اصلی صندوق
                fund = db.query(Fund).filter(Fund.reg_no == reg_no).first()
                if not fund:
                    fund = Fund(reg_no=reg_no, name=name, fund_type=f_type)
                    db.add(fund)
                
                # آپدیت فیلدهای قیمتی
                fund.nav_stat = nav_stat
                fund.nav_sub = item.get("navSub")
                fund.nav_red = item.get("navRed")
                fund.net_asset = net_asset
                fund.units = item.get("units")
                
                # آپدیت اطلاعات هویتی و بازدهی
                fund.manager = item.get("manager", "نامشخص")
                fund.day30_return = item.get("day30Return")
                fund.day90_return = item.get("day90Return")
                fund.day365_return = item.get("day365Return")
                
                # آپدیت ترکیب دارایی
                fund.portfolio_stock = item.get("portfolioStock")
                fund.portfolio_bond = item.get("portfolioBond")
                fund.portfolio_deposit = item.get("portfolioDeposit")
                
                fund.fund_type = f_type
                fund.last_updated = datetime.utcnow()
                
                # اضافه کردن به تاریخچه
                history_record = FundHistory(
                    fund_reg_no=reg_no,
                    nav_stat=nav_stat,
                    net_asset=net_asset
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