from contextlib import asynccontextmanager
from fastapi import FastAPI
from apscheduler.schedulers.background import BackgroundScheduler

from core.database import engine, Base
from services.tasks import update_funds_data, update_etf_market_data
from routers.web import router

# ساخت جداول دیتابیس در صورت عدم وجود
Base.metadata.create_all(bind=engine)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # ۱. اجرای تسک‌ها در زمان استارت برای دریافت اولیه دیتا
    update_funds_data()
    update_etf_market_data()
    
    # ۲. راه‌اندازی زمان‌بند (Scheduler)
    scheduler = BackgroundScheduler()
    scheduler.add_job(update_funds_data, 'interval', minutes=1)
    scheduler.add_job(update_etf_market_data, 'interval', minutes=1)
    scheduler.start()
    
    yield
    
    # ۳. خاموش کردن زمان‌بند در زمان قطع سرور
    scheduler.shutdown()

# مقداردهی اولیه اپلیکیشن
app = FastAPI(
    title="Quant Fund Dashboard",
    description="Live Dashboard for TSETMC Funds and ETFs",
    version="1.0.0",
    lifespan=lifespan
)

# اضافه کردن مسیرها (Routes) به اپلیکیشن
app.include_router(router)