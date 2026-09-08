import logging
from datetime import datetime, timedelta
from dateutil import parser # pip install python-dateutil
from core.database import SessionLocal
from core.repositories import FundRepository
from services.providers import TSETMCProvider
from services.preprocessing import clean_fund_data

logger = logging.getLogger(__name__)
provider = TSETMCProvider()
FUND_TYPES = [4, 5, 6, 7, 11, 12, 13, 14, 16, 17]

def bootstrap_fund_history(db, fund_repo, reg_no: int):
    """مرحله 1: اگر دیتابیس خالی است، تاریخچه 90 روزه را می‌گیریم"""
    latest_time = fund_repo.get_latest_observation_time(reg_no)
    if latest_time is not None:
        return # دیتابیس خالی نیست

    logger.info(f"Bootstrapping history for Fund {reg_no}...")
    history_data = provider.fetch_fund_history_detail(reg_no)
    
    if not history_data:
        return

    # فقط 90 رکورد آخر (90 روز)
    for item in history_data[:90]:
        try:
            # زمان ثبت دیتا در بورس
            record_date = item.get("recordDate")
            if not record_date:
                continue
                
            observed_at = parser.parse(record_date)
            
            # ذخیره در دیتابیس با مکانیزم UPSERT
            fund_repo.upsert_fund_history(
                reg_no=reg_no,
                nav_stat=item.get("navStat") or 0.0,
                net_asset=item.get("netAsset") or 0.0,
                observed_at=observed_at
            )
        except Exception as e:
            logger.debug(f"Error parsing history row for fund {reg_no}: {e}")
            continue

def sync_funds_pipeline():
    """مرحله 2: منطق اصلی اجرای لایو (کرون‌جاب)"""
    logger.info("Starting Data Pipeline Sync...")
    db = SessionLocal()
    fund_repo = FundRepository(db)
    
    try:
        for f_type in FUND_TYPES:
            funds_data = provider.fetch_funds_by_type(f_type)
            if not funds_data:
                continue
                
            for item in funds_data:
                clean_item = clean_fund_data(item)
                reg_no = clean_item['reg_no']
                if reg_no == 0: continue
                
                # آپدیت مشخصات اصلی صندوق
                fund_repo.upsert_fund(reg_no, clean_item['name'], f_type, clean_item)
                
                # 1. Bootstrap: اگر دیتابیس تاریخچه نداشت، 90 روز را بگیر
                bootstrap_fund_history(db, fund_repo, reg_no)
                
                # 2. Incremental Sync: لاجیک اضافه کردن نقطه جدید
                # در دیتای لایو بورس، observed_at معمولا recordDate یا ترکیب تاریخ و ساعت است
                record_date_str = item.get("recordDate")
                if not record_date_str:
                    continue
                    
                observed_at = parser.parse(record_date_str)
                latest_db_time = fund_repo.get_latest_observation_time(reg_no)
                
                # اگر دیتای بورس از دیتای ما جدیدتر یا مساوی بود (برای Correction) آپسرت می‌کنیم
                if not latest_db_time or observed_at >= latest_db_time:
                    fund_repo.upsert_fund_history(
                        reg_no=reg_no,
                        nav_stat=clean_item['nav_stat'],
                        net_asset=clean_item['net_asset'],
                        observed_at=observed_at
                    )
        db.commit()
        logger.info("Pipeline Sync Completed Successfully.")
    except Exception as e:
        db.rollback()
        logger.error(f"Pipeline Error: {e}")
    finally:
        db.close()