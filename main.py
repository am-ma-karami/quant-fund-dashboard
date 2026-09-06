from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Depends
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from apscheduler.schedulers.background import BackgroundScheduler

from database import engine, Base, get_db
from models import Fund, FundHistory
from tasks import update_funds_data

# ایجاد جداول در دیتابیس
Base.metadata.create_all(bind=engine)

templates = Jinja2Templates(directory="templates")

# راه‌اندازی Scheduler برای اجرای Task هر ۱ دقیقه
@asynccontextmanager
async def lifespan(app: FastAPI):
    # هنگام روشن شدن سرور یک بار دیتا را می‌گیریم
    update_funds_data() 
    
    scheduler = BackgroundScheduler()
    scheduler.add_job(update_funds_data, 'interval', minutes=1)
    scheduler.start()
    yield
    scheduler.shutdown()

app = FastAPI(lifespan=lifespan)

@app.get("/")
def read_dashboard(request: Request, db: Session = Depends(get_db)):
    # دریافت لیست تمام صندوق‌ها برای نمایش در صفحه اول
    funds = db.query(Fund).order_by(Fund.net_asset.desc()).all()
    return templates.TemplateResponse("index.html", {"request": request, "funds": funds})

@app.get("/fund/{reg_no}")
def read_fund_detail(request: Request, reg_no: int, db: Session = Depends(get_db)):
    fund = db.query(Fund).filter(Fund.reg_no == reg_no).first()
    
    # واکشی ۳۰ دیتای آخر (تاریخچه) برای رسم نمودار
    histories = db.query(FundHistory).filter(FundHistory.fund_reg_no == reg_no).order_by(FundHistory.recorded_at.asc()).limit(60).all()
    
    labels = [h.recorded_at.strftime('%H:%M') for h in histories]
    data = [h.nav_stat for h in histories]
    
    return templates.TemplateResponse("fund_detail.html", {
        "request": request, 
        "fund": fund,
        "labels": labels,
        "data": data
    })