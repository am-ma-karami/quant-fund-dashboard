from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi_cache.decorator import cache
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import timedelta

from core.database import get_db
from core.repositories import FundRepository, ETFRepository, BenchmarkRepository, iran_time
from core.models import Fund, FundHistory, ETFMarket, BenchmarkHistory
from core.benchmark import TEHRAN_TOTAL_INDEX
from services.analytics import (
    active_return,
    cumulative_return,
    drawdown_series,
    fund_flows,
    index_to_100,
    cumulative_sum,
)
from services.etf_analytics import calculate_premium_zscore

router = APIRouter()
templates = Jinja2Templates(directory="templates")

FUND_CATEGORIES = {
    4: "درآمد ثابت (Fixed Income)", 5: "کالا (Commodity)", 6: "سهامی (Stock)",
    7: "مختلط (Mixed)", 11: "بازارگردانی (Market Making)", 12: "جسورانه (VC)",
    13: "پروژه (Project)", 14: "املاک و مستغلات (REIT)", 16: "خصوصی (Private)",
    17: "صندوق در صندوق (Fund in Fund)"
}

@router.get("/")
def read_dashboard(
    request: Request
):
    categories = [
        {
            "id": key,
            "name": value
        }
        for key, value in FUND_CATEGORIES.items()
    ]

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "categories": categories
        }
    )

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
    
    # اگر صندوق هنوز دانلود نشده بود، 404 بده
    if not fund:
        raise HTTPException(status_code=404, detail="صندوق در حال بروزرسانی است یا وجود ندارد.")
        
    cutoff = iran_time() - timedelta(days=30)
    recent_histories = repo.get_fund_history(reg_no, since=cutoff)
    histories = recent_histories or repo.get_fund_history(reg_no, limit=30)
    latest_history_at = repo.get_latest_observation_time(reg_no)
    labels = [h.observed_at.strftime('%Y-%m-%d') for h in histories]
    data = [h.nav_stat for h in histories]
    
    return templates.TemplateResponse("fund_detail.html", {
        "request": request, "fund": fund, "labels": labels, "data": data
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

    result = []
    for e in etfs:
        fund = db.query(Fund).filter(Fund.ins_code == e.ins_code).first()
        nav_stat = fund.nav_stat if fund else None

        premium = None
        if nav_stat and nav_stat > 0 and e.last_price:
            premium = ((e.last_price - nav_stat) / nav_stat) * 100

        result.append({
            "ins_code": e.ins_code, "symbol": e.symbol, "name": e.name,
            "last_price": e.last_price, "closing_price": e.closing_price,
            "price_change": e.price_change, "total_trades": e.total_trades,
            "nav_stat": nav_stat,
            "premium": round(premium, 2) if premium else None,
            "last_updated": e.last_updated.strftime('%H:%M:%S') if e.last_updated else ""
        })
    return result

@router.get("/api/fund/{reg_no}/chart")
def api_fund_chart(reg_no: int, db: Session = Depends(get_db)):
    repo = FundRepository(db)
    etf_repo = ETFRepository(db)
    fund = repo.get_fund_by_reg_no(reg_no)

    if fund is None:
        raise HTTPException(
            status_code=404,
            detail=f"Fund {reg_no} not found"
        )
    
    cutoff = iran_time() - timedelta(days=30)
    recent_histories = repo.get_fund_history(reg_no, limit=90, since=cutoff)
    anchor = repo.get_latest_history_before(reg_no, cutoff)
    latest_history_at = repo.get_latest_observation_time(reg_no)
    chart_history = []

    # The upstream feed is change-based, not daily. Carry the last known NAV
    # into the window so a quiet month renders as a valid flat step series.
    if anchor:
        chart_history.append({
            "timestamp": cutoff.isoformat(),
            "nav_stat": anchor.nav_stat or 0,
            "net_asset": anchor.net_asset or 0,
            "is_anchor": True,
        })

    chart_history.extend({
        "timestamp": h.observed_at.isoformat(),
        "nav_stat": h.nav_stat or 0,
        "net_asset": h.net_asset or 0,
        "is_anchor": False,
    } for h in recent_histories)

    live_timestamp = fund.last_updated or iran_time()
    if not chart_history or chart_history[-1]["timestamp"] != live_timestamp.isoformat():
        chart_history.append({
            "timestamp": live_timestamp.isoformat(),
            "nav_stat": fund.nav_stat or 0,
            "net_asset": fund.net_asset or 0,
            "is_live": True,
        })

    # Align ETF price history with NAV history by date
    nav_by_date = {}
    for h in recent_histories:
        if h.observed_at and h.nav_stat is not None:
            nav_by_date[h.observed_at.strftime("%Y-%m-%d")] = h.nav_stat

    labels = sorted(nav_by_date.keys())
    nav_data = [nav_by_date[date] for date in labels]
    price_data = [None] * len(labels)

    if fund.is_etf and fund.ins_code:
        etf_histories = etf_repo.get_etf_history(fund.ins_code, limit=90)
        price_by_date = {}
        for h in etf_histories:
            if h.observed_at and h.closing_price is not None:
                price_by_date[h.observed_at.strftime("%Y-%m-%d")] = h.closing_price
        price_data = [price_by_date.get(date) for date in labels]

    risk_metrics = repo.get_fund_risk_metrics(reg_no)

    benchmark_repo = BenchmarkRepository(db)
    benchmark_history = benchmark_repo.get_history(
        TEHRAN_TOTAL_INDEX.code,
        limit=252,
    )

    benchmark_return = None
    if len(benchmark_history) >= 2:
        benchmark_prices = [b.value for b in benchmark_history]
        benchmark_return = cumulative_return(benchmark_prices)

    fund_return = None
    if fund.day365_return is not None:
        fund_return = fund.day365_return / 100.0

    active_return_value = active_return(
        fund_return,
        benchmark_return,
    )

    # مقایسه با شاخص: هم‌ترازی با تاریخ‌های NAV و نرمال‌سازی به ۱۰۰
    benchmark_by_date = {
        h.observed_at.strftime("%Y-%m-%d"): h.value
        for h in benchmark_history
    }

    benchmark_aligned = []
    last_benchmark = None
    for date in labels:
        value = benchmark_by_date.get(date, last_benchmark)
        if value is not None:
            last_benchmark = value
        benchmark_aligned.append(value)

    comparison = None
    first_common = next(
        (
            index
            for index, (nav, bench) in enumerate(
                zip(nav_data, benchmark_aligned)
            )
            if nav and bench
        ),
        None,
    )
    if first_common is not None:
        comparison = {
            "labels": labels[first_common:],
            "fund": index_to_100(nav_data[first_common:]),
            "benchmark": index_to_100(benchmark_aligned[first_common:]),
        }

    # سری دراودان و جریان پول از تاریخچه هم‌تراز
    history_by_date = {
        h.observed_at.strftime("%Y-%m-%d"): h
        for h in recent_histories
    }
    aum_data = [
        history_by_date[date].net_asset if history_by_date.get(date) else None
        for date in labels
    ]
    flows_per_period = fund_flows(nav_data, aum_data)
    flows = {
        "labels": labels,
        "per_period": flows_per_period,
        "cumulative": cumulative_sum(flows_per_period),
    }
    drawdown = {
        "labels": labels,
        "values": drawdown_series(nav_data),
    }

    return {
        "fund": {
            "reg_no": fund.reg_no,
            "name": fund.name,
            "nav_stat": fund.nav_stat or 0,
            "nav_sub": fund.nav_sub or 0,
            "nav_red": fund.nav_red or 0,
            "last_updated": (
                fund.last_updated.isoformat()
                if fund.last_updated
                else None
            )
        },
        "risk": risk_metrics,
        "performance": {
            "return_30d": fund.day30_return,
            "return_90d": fund.day90_return,
            "return_365d": fund.day365_return,
            "active_return": active_return_value,
        },
        "history": chart_history,
        "labels": labels,
        "nav_data": nav_data,
        "price_data": price_data,
        "is_etf": bool(fund.is_etf),
        "window_start": cutoff.isoformat(),
        "has_changes_in_window": bool(recent_histories),
        "latest_history_at": latest_history_at.isoformat() if latest_history_at else None,
        "comparison": comparison,
        "drawdown": drawdown,
        "flows": flows,
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

    # گرفتن تاریخچه نوسانات امروز
    histories = repo.get_etf_history(ins_code)

    historical_premiums = repo.get_recent_premiums(
        ins_code,
        limit=60,
    )

    premium_zscore = calculate_premium_zscore(
        etf.premium_discount,
        historical_premiums,
    )

    # سری پریمیوم intraday (همان ردیف‌های امروز که premium_discount دارند)
    premium_intraday = {
        "labels": [h.observed_at.strftime('%H:%M') for h in histories],
        "values": [
            h.premium_discount
            if h.premium_discount is not None
            else None
            for h in histories
        ],
    }

    # سری روزانه پریمیوم (۹۰ روز): قیمت پایانی ETF در برابر NAV صندوق متناظر
    premium_series = {
        "labels": [],
        "values": [],
        "fund_reg_no": None,
    }
    mapped_fund = db.query(Fund).filter(Fund.ins_code == ins_code).first()
    if mapped_fund is not None:
        daily_rows = repo.get_daily_price_history(ins_code, days=90)
        price_by_date = {}
        for row in daily_rows:
            if row.observed_at is None:
                continue
            price = row.closing_price or row.last_price
            if price:
                price_by_date[row.observed_at.date().isoformat()] = price

        fund_navs = (
            db.query(FundHistory)
            .filter(FundHistory.fund_reg_no == mapped_fund.reg_no)
            .order_by(FundHistory.observed_at.desc())
            .limit(150)
            .all()
        )
        nav_by_date = {
            h.observed_at.date().isoformat(): h.nav_stat
            for h in fund_navs
            if h.observed_at is not None and h.nav_stat
        }

        labels = []
        values = []
        for date in sorted(set(price_by_date) & set(nav_by_date)):
            price = price_by_date[date]
            nav = nav_by_date[date]
            if not nav:
                continue
            labels.append(date)
            values.append(round(((price / nav) - 1.0) * 100.0, 2))

        premium_series = {
            "labels": labels,
            "values": values,
            "fund_reg_no": mapped_fund.reg_no,
        }

    return {
        "labels": [h.observed_at.strftime('%H:%M') for h in histories],
        "data": [h.last_price for h in histories],
        "last_price": etf.last_price,
        "closing_price": etf.closing_price,
        "price_change": etf.price_change,
        "total_trades": etf.total_trades,
        "total_volume": etf.total_volume,
        "total_value": etf.total_value,
        "price_min": etf.price_min,
        "price_max": etf.price_max,
        "price_first": etf.price_first,
        "price_yesterday": etf.price_yesterday,
        "nav": etf.nav,
        "nav_sub": etf.nav_sub,
        "nav_red": etf.nav_red,
        "premium": etf.premium_discount,
        "premium_zscore": premium_zscore,
        "premium_intraday": premium_intraday,
        "premium_series": premium_series,
        "last_updated": etf.last_updated.strftime('%H:%M:%S') if etf.last_updated else ""
    }


@router.get("/api/market-pulse")
@cache(expire=15)
def api_market_pulse(db: Session = Depends(get_db)):
    """API برای آپدیت لایو داشبورد فرماندهی"""
    repo = ETFRepository(db)
    return repo.get_market_pulse()


@router.get("/api/dashboard/market-pulse")
@cache(expire=15)
def api_dashboard_market_pulse(db: Session = Depends(get_db)):
    """Alias for /api/market-pulse for dashboard compatibility"""
    repo = ETFRepository(db)
    return repo.get_market_pulse()


@router.get("/api/dashboard/top-funds")
@cache(expire=30)
def api_top_funds(
    db: Session = Depends(get_db)
):
    repo = FundRepository(db)

    funds = repo.get_top_funds_by_return(
        limit=10
    )

    return [
        {
            "rank": index + 1,
            "reg_no": fund.reg_no,
            "name": fund.name,
            "return_30d": fund.day30_return or 0
        }
        for index, fund in enumerate(funds)
    ]


@router.get("/api/dashboard/risk-return")
@cache(expire=3600)
def api_risk_return(
    db: Session = Depends(get_db)
):
    """نقشه ریسک/بازده صندوق‌های سهامی: x=نوسان سالانه، y=بازده ۹۰ روزه، اندازه=AUM."""
    repo = FundRepository(db)

    funds = repo.get_funds_by_type(6)

    since = iran_time() - timedelta(days=150)
    volatility_map = repo.get_volatility_map(since)

    points = []
    for fund in funds:
        volatility = volatility_map.get(fund.reg_no)
        if volatility is None or fund.day90_return is None:
            continue
        points.append({
            "reg_no": fund.reg_no,
            "name": fund.name,
            "volatility": round(volatility * 100, 2),
            "return_90d": round(fund.day90_return, 2),
            "aum": round(fund.net_asset or 0),
        })

    return points


@router.get("/api/dashboard/heatmap")
@cache(expire=60)
def api_dashboard_heatmap(
    db: Session = Depends(get_db)
):
    repo = FundRepository(db)

    funds = repo.get_heatmap_data(limit=50)

    return [
        {
            "name": (
                f.name
                .replace("صندوق سرمایه گذاری ", "")
                .replace("صندوق ", "")
                [:15]
            ),
            "value": f.net_asset or 0,
            "colorValue": f.day30_return or 0,
            "reg_no": f.reg_no
        }
        for f in funds
    ]


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


@router.get("/health")
def health():
    return {
        "status": "ok"
    }


@router.get("/api/health/data")
def api_data_quality(
    db: Session = Depends(get_db),
):
    """وضعیت کیفیت داده و پوشش آخرین سینک صندوق‌ها."""
    from core.models import SyncStatus

    status = db.query(SyncStatus).filter(
        SyncStatus.job_name == "fund_sync"
    ).first()

    if not status:
        return {
            "status": "unknown",
            "expected_funds": 0,
            "received_funds": 0,
            "valid_funds": 0,
            "coverage": 0.0,
            "failed_funds": 0,
            "last_successful_sync": None,
            "latency_ms": None,
            "provider": "TSETMC",
        }

    expected = status.expected_count or 0
    received = status.received_count or 0
    coverage = (received / expected) if expected > 0 else 0.0

    return {
        "status": status.status,
        "expected_funds": expected,
        "received_funds": received,
        "valid_funds": status.valid_count or 0,
        "coverage": round(coverage, 4),
        "failed_funds": status.failed_count or 0,
        "last_successful_sync": (
            status.last_success_at.isoformat()
            if status.last_success_at
            else None
        ),
        "latency_ms": status.duration_ms,
        "provider": status.provider or "TSETMC",
        "quality_score": status.quality_score,
    }


@router.get("/api/dashboard/history-backfill")
def api_history_backfill_progress(db: Session = Depends(get_db)):
    from sqlalchemy import func
    from core.repositories import FundRepository

    repo = FundRepository(db)

    eligible = db.query(Fund).filter(Fund.net_asset > 0)
    total_eligible = eligible.count()

    history_query = db.query(
        FundHistory.fund_reg_no,
        func.count(FundHistory.id).label("hist_count"),
    ).group_by(FundHistory.fund_reg_no).subquery()

    complete = (
        eligible.outerjoin(history_query, Fund.reg_no == history_query.c.fund_reg_no)
        .filter(func.coalesce(history_query.c.hist_count, 0) >= 90)
        .count()
    )

    total_records = db.query(func.count(FundHistory.id)).scalar() or 0
    funds_with_any_history = db.query(func.count(func.distinct(FundHistory.fund_reg_no))).scalar() or 0

    missing = total_eligible - complete
    pct = (complete / total_eligible * 100) if total_eligible else 0

    return {
        "total": total_eligible,
        "complete": complete,
        "missing": missing,
        "percentage": round(pct, 1),
        "total_records": total_records,
        "funds_with_any_history": funds_with_any_history,
    }


@router.get("/ready")
def readiness(
    db: Session = Depends(get_db)
):
    db.execute(text("SELECT 1"))
    
    return {
        "status": "ready"
    }
