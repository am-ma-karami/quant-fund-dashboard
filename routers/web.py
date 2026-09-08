from fastapi import APIRouter, Request, Depends
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from fastapi import APIRouter, Request, Depends, HTTPException

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
    fund_repo = FundRepository(db)
    etf_repo = ETFRepository(db)
    
    categories = [{"id": k, "name": v} for k, v in FUND_CATEGORIES.items()]
    
    top_funds = fund_repo.get_top_funds_by_return(limit=10)
    top_funds_names = [f.name for f in top_funds]
    top_funds_returns = [f.day30_return for f in top_funds]
    
    # دریافت دیتای نبض بازار
    pulse = etf_repo.get_market_pulse()
    
    return templates.TemplateResponse("index.html", {
        "request": request, 
        "categories": categories,
        "top_funds_names": top_funds_names,
        "top_funds_returns": top_funds_returns,
        "pulse": pulse 
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
    
    labels = [h.observed_at.strftime('%H:%M') for h in histories]
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
    
    labels = [h.observed_at.strftime('%H:%M') for h in histories]
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

    if fund is None:
        raise HTTPException(
            status_code=404,
            detail=f"Fund {reg_no} not found"
        )
    
    histories = repo.get_fund_history(reg_no)
    return {
        "labels": [h.observed_at.strftime('%H:%M') for h in histories],
        "data": [h.nav_stat for h in histories],
        "nav_stat": fund.nav_stat, "nav_sub": fund.nav_sub, "nav_red": fund.nav_red,
        "last_updated": fund.last_updated.strftime('%Y-%m-%d %H:%M:%S')
    }

@router.get("/api/etf/{ins_code}/chart")
def api_etf_chart(ins_code: str, db: Session = Depends(get_db)):
    repo = ETFRepository(db)

    etf = repo.get_etf_by_ins_code(ins_code)

    if etf is None:
        raise HTTPException(
            status_code=404,
            detail=f"ETF {ins_code} not found"
        )

    histories = repo.get_etf_history(ins_code)
    return {
        "labels": [h.observed_at.strftime('%H:%M') for h in histories],
        "data": [h.last_price for h in histories],
        "last_price": etf.last_price, "closing_price": etf.closing_price,
        "last_updated": etf.last_updated.strftime('%Y-%m-%d %H:%M:%S')
    }


# @router.get("/etf-to-fund/{ins_code}")
# def redirect_etf_to_fund(ins_code: str, db: Session = Depends(get_db)):
#     """
#     موتور جستجوی هوشمند برای مپ کردن دیتای تابلوی معاملات به دیتای پورتفوی صندوق.
#     چون API بورس کلید مشترکی نمی‌دهد، ما بر اساس «نماد» در «نام صندوق» سرچ می‌کنیم.
#     """
#     repo = ETFRepository(db)
#     etf = repo.get_etf_by_ins_code(ins_code)
    
#     # اگر اصلا چنین کدی در تابلوی لایو ما نبود، برگرد به صفحه تابلو
#     if not etf:
#         return RedirectResponse(url="/etf-live")
        
#     # جستجو در جدول صندوق‌ها با استفاده از LIKE (یا ilike برای حساس نبودن به حروف)
#     # در SQLAlchemy معادل LIKE %symbol% همان متد contains است:
#     matched_fund = db.query(Fund).filter(Fund.name.contains(etf.symbol)).first()
    
#     if matched_fund:
#         # اگر صندوق پیدا شد، کاربر را به صورت خودکار به صفحه داشبورد صندوق شوت کن
#         return RedirectResponse(url=f"/fund/{matched_fund.reg_no}")
#     else:
#         # اگر پیدا نشد (مثلا اسمش خیلی فرق داشت)، کاربر را بفرست به صفحه چارت ساده خود ETF
#         return RedirectResponse(url=f"/etf/{ins_code}")


@router.get("/api/market-pulse")
def api_market_pulse(db: Session = Depends(get_db)):
    """API برای آپدیت لایو داشبورد فرماندهی"""
    repo = ETFRepository(db)
    return repo.get_market_pulse()


@router.get("/api/heatmap")
def api_heatmap(db: Session = Depends(get_db)):
    repo = FundRepository(db)
    funds = repo.get_heatmap_data(limit=50)
    
    data = []
    for f in funds:
        # نام صندوق‌ها را کوتاه می‌کنیم تا در مربع‌های نقشه جا شوند
        short_name = f.name.replace("صندوق سرمایه گذاری ", "").replace("صندوق ", "")[:15]
        data.append({
            "name": short_name,
            "value": f.net_asset,            # تعیین کننده سایز مربع
            "colorValue": f.day30_return,    # تعیین کننده رنگ مربع
            "reg_no": f.reg_no               # برای لینک دادن
        })
    return data


# مسیر باز کردن صفحه Screener
@router.get("/screener")
def read_screener(request: Request):
    categories = [{"id": k, "name": v} for k, v in FUND_CATEGORIES.items()]
    return templates.TemplateResponse("screener.html", {"request": request, "categories": categories})

# مسیر API بهینه شده و کش شده برای دیتای Screener
@router.get("/api/screener-data")
def api_screener_data(db: Session = Depends(get_db)):
    repo = FundRepository(db)
    funds = repo.get_all_funds_for_screener()
    
    return [{
        "reg_no": f.reg_no,
        "name": f.name,
        "fund_type": f.fund_type,
        "manager": f.manager or "نامشخص",
        "net_asset": f.net_asset or 0,
        "nav_stat": f.nav_stat or 0,
        "day30_return": f.day30_return or 0,
        "day365_return": f.day365_return or 0,
        "portfolio_stock": f.portfolio_stock or 0
    } for f in funds]