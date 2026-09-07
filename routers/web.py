from fastapi import APIRouter, Request, Depends
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

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