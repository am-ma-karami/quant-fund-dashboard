import logging
import sys
from apscheduler.schedulers.blocking import BlockingScheduler
from core.database import engine, Base
from services.fund_sync import sync_funds_pipeline

logging.basicConfig(stream=sys.stdout, level=logging.INFO)
logger = logging.getLogger("WORKER")

# ساخت جداول در صورت عدم وجود
Base.metadata.create_all(bind=engine)

if __name__ == "__main__":
    logger.info("Starting Quant Worker Service...")
    
    # یک بار اجرا در زمان روشن شدن
    sync_funds_pipeline()
    
    # اجرای مداوم هر 1 دقیقه
    scheduler = BlockingScheduler()
    scheduler.add_job(sync_funds_pipeline, 'interval', minutes=1)
    
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        pass