from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Depends
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from apscheduler.schedulers.background import BackgroundScheduler

from models import Fund, FundHistory, ETFMarket, ETFMarketHistory
from tasks import update_funds_data, update_etf_market_data

from database import engine, Base, get_db
from models import Fund, FundHistory
from tasks import update_funds_data

Base.metadata.create_all(bind=engine)
templates = Jinja2Templates(directory="templates")

# دیکشنری نام دسته‌بندی‌ها
FUND_CATEGORIES = {
    4: "درآمد ثابت (Fixed Income)",
    5: "کالا (Commodity)",
    6: "سهامی (Stock)",
    7: "مختلط (Mixed)",
    11: "بازارگردانی (Market Making)",
    12: "جسورانه (VC)",
    13: "پروژه (Project)",
    14: "املاک و مستغلات (REIT)",
    16: "خصوصی (Private)",
    17: "صندوق در صندوق (Fund in Fund)"
}

@asynccontextmanager
async def lifespan(app: FastAPI):
    # ران کردن تسک‌ها در زمان استارت
    update_funds_data()
    update_etf_market_data()
    
    scheduler = BackgroundScheduler()
    scheduler.add_job(update_funds_data, 'interval', minutes=1)
    scheduler.add_job(update_etf_market_data, 'interval', minutes=1) # تسک جدید
    scheduler.start()
    yield
    scheduler.shutdown()

app = FastAPI(lifespan=lifespan)

@app.get("/")
def read_dashboard(request: Request):
    # تبدیل دیکشنری به لیستی از آبجکت‌ها برای فرانت‌اند
    categories = [{"id": k, "name": v} for k, v in FUND_CATEGORIES.items()]
    return templates.TemplateResponse("index.html", {"request": request, "categories": categories})

@app.get("/category/{type_id}")
def read_category(request: Request, type_id: int, db: Session = Depends(get_db)):
    category_name = FUND_CATEGORIES.get(type_id, "دسته‌بندی نامشخص")
    funds = db.query(Fund).filter(Fund.fund_type == type_id).order_by(Fund.net_asset.desc()).all()
    return templates.TemplateResponse("category.html", {
        "request": request, 
        "funds": funds, 
        "category_name": category_name
    })

@app.get("/fund/{reg_no}")
def read_fund_detail(request: Request, reg_no: int, db: Session = Depends(get_db)):
    fund = db.query(Fund).filter(Fund.reg_no == reg_no).first()
    histories = db.query(FundHistory).filter(FundHistory.fund_reg_no == reg_no).order_by(FundHistory.recorded_at.asc()).limit(60).all()
    
    labels = [h.recorded_at.strftime('%H:%M') for h in histories]
    data = [h.nav_stat for h in histories]
    
    return templates.TemplateResponse("fund_detail.html", {
        "request": request, 
        "fund": fund,
        "labels": labels,
        "data": data
    })


@app.get("/etf-live")
def read_etf_live(request: Request, db: Session = Depends(get_db)):
    etfs = db.query(ETFMarket).order_by(ETFMarket.total_trades.desc()).all()
    return templates.TemplateResponse("etf_live.html", {"request": request, "etfs": etfs})