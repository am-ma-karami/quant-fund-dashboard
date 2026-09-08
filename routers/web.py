from fastapi import APIRouter, Request, Depends
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session


from fastapi.responses import RedirectResponse

from core.database import get_db
from core.repositories import FundRepository, ETFRepository

router = APIRouter()
templates = Jinja2Templates(directory="templates")

FUND_CATEGORIES = {
    4: "درآمد ثابت (Fixed Income)", 5: "کالا (Commodity)", 6: "سهامی (Stock)",
    7: "مختلط (Mixed)", 11: "بازارگردانی (Market Making)", 12: "جسورانه (VC)",
    13: "پروژه (Project)", 14: "املاک و مستغلات (REIT)", 16: "خصوصی (Private)",
    17: "صندوق در صندوق (Fund in Fund)"
}

@router.get("/")
def read_dashboard(request: Request, db: Session = Depends(get_db)):
    repo = FundRepository(db)
    categories = [{"id": k, "name": v} for k, v in FUND_CATEGORIES.items()]
    
    top_funds = repo.get_top_funds_by_return(limit=10)
    top_funds_names = [f.name for f in top_funds]
    top_funds_returns = [f.day30_return for f in top_funds]
    
    return templates.TemplateResponse("index.html", {
        "request": request, 
        "categories": categories,
        "top_funds_names": top_funds_names,
        "top_funds_returns": top_funds_returns
    })

@router.get("/category/{type_id}")
def read_category(request: Request, type_id: int, db: Session = Depends(get_db)):
    repo = FundRepository(db)
    category_name = FUND_CATEGORIES.get(type_id, "دسته‌بندی نامشخص")
    funds = repo.get_funds_by_type(type_id)
    
    return templates.TemplateResponse("category.html", {
        "request": request, 
        "funds": funds, 
        "category_name": category_name
    })

@router.get("/fund/{reg_no}")
def read_fund_detail(request: Request, reg_no: int, db: Session = Depends(get_db)):
    repo = FundRepository(db)
    fund = repo.get_fund_by_reg_no(reg_no)
    histories = repo.get_fund_history(reg_no)
    
    labels = [h.recorded_at.strftime('%H:%M') for h in histories]
    data = [h.nav_stat for h in histories]
    
    return templates.TemplateResponse("fund_detail.html", {
        "request": request, 
        "fund": fund,
        "labels": labels,
        "data": data
    })

@router.get("/etf-live")
def read_etf_live(request: Request, db: Session = Depends(get_db)):
    repo = ETFRepository(db)
    etfs = repo.get_all_etfs()
    return templates.TemplateResponse("etf_live.html", {"request": request, "etfs": etfs})



@router.get("/etf/{ins_code}")
def read_etf_detail(request: Request, ins_code: str, db: Session = Depends(get_db)):
    repo = ETFRepository(db)
    etf = repo.get_etf_by_ins_code(ins_code)
    histories = repo.get_etf_history(ins_code)
    
    labels = [h.recorded_at.strftime('%H:%M') for h in histories]
    data = [h.last_price for h in histories]
    
    return templates.TemplateResponse("etf_detail.html", {
        "request": request, "etf": etf, "labels": labels, "data": data
    })

# --- مسیرهای API برای آپدیت بدون رفرش ---

@router.get("/api/etfs")
def api_get_etfs(db: Session = Depends(get_db)):
    repo = ETFRepository(db)
    etfs = repo.get_all_etfs()
    return [{
        "ins_code": e.ins_code, "symbol": e.symbol, "name": e.name,
        "last_price": e.last_price, "closing_price": e.closing_price,
        "price_change": e.price_change, "total_trades": e.total_trades,
        "last_updated": e.last_updated.strftime('%H:%M:%S') if e.last_updated else ""
    } for e in etfs]

@router.get("/api/fund/{reg_no}/chart")
def api_fund_chart(reg_no: int, db: Session = Depends(get_db)):
    repo = FundRepository(db)
    fund = repo.get_fund_by_reg_no(reg_no)
    histories = repo.get_fund_history(reg_no)
    return {
        "labels": [h.recorded_at.strftime('%H:%M') for h in histories],
        "data": [h.nav_stat for h in histories],
        "nav_stat": fund.nav_stat, "nav_sub": fund.nav_sub, "nav_red": fund.nav_red,
        "last_updated": fund.last_updated.strftime('%Y-%m-%d %H:%M:%S')
    }

@router.get("/api/etf/{ins_code}/chart")
def api_etf_chart(ins_code: str, db: Session = Depends(get_db)):
    repo = ETFRepository(db)
    etf = repo.get_etf_by_ins_code(ins_code)
    histories = repo.get_etf_history(ins_code)
    return {
        "labels": [h.recorded_at.strftime('%H:%M') for h in histories],
        "data": [h.last_price for h in histories],
        "last_price": etf.last_price, "closing_price": etf.closing_price,
        "last_updated": etf.last_updated.strftime('%Y-%m-%d %H:%M:%S')
    }


@router.get("/etf-to-fund/{ins_code}")
def redirect_etf_to_fund(ins_code: str, db: Session = Depends(get_db)):
    """
    موتور جستجوی هوشمند برای مپ کردن دیتای تابلوی معاملات به دیتای پورتفوی صندوق.
    چون API بورس کلید مشترکی نمی‌دهد، ما بر اساس «نماد» در «نام صندوق» سرچ می‌کنیم.
    """
    repo = ETFRepository(db)
    etf = repo.get_etf_by_ins_code(ins_code)
    
    # اگر اصلا چنین کدی در تابلوی لایو ما نبود، برگرد به صفحه تابلو
    if not etf:
        return RedirectResponse(url="/etf-live")
        
    # جستجو در جدول صندوق‌ها با استفاده از LIKE (یا ilike برای حساس نبودن به حروف)
    # در SQLAlchemy معادل LIKE %symbol% همان متد contains است:
    matched_fund = db.query(Fund).filter(Fund.name.contains(etf.symbol)).first()
    
    if matched_fund:
        # اگر صندوق پیدا شد، کاربر را به صورت خودکار به صفحه داشبورد صندوق شوت کن
        return RedirectResponse(url=f"/fund/{matched_fund.reg_no}")
    else:
        # اگر پیدا نشد (مثلا اسمش خیلی فرق داشت)، کاربر را بفرست به صفحه چارت ساده خود ETF
        return RedirectResponse(url=f"/etf/{ins_code}")