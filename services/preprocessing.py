import logging

logger = logging.getLogger(__name__)

def clean_fund_data(raw_data: dict) -> dict:
    """
    پیش‌پردازش و پاک‌سازی دیتای خام دریافتی از API بورس
    تبدیل Null ها به صفر، نرمال‌سازی متن‌ها و کنترل محدوده‌ی درصدها
    """
    cleaned = {}
    
    # 1. Validation (اعتبارسنجی): بررسی شماره ثبت
    try:
        cleaned['reg_no'] = int(raw_data.get("regNo", 0))
    except (TypeError, ValueError):
        cleaned['reg_no'] = 0

    # 2. Handling Nulls (جایگزینی مقادیر خالی)
    cleaned['nav_stat'] = raw_data.get("navStat") or 0.0
    cleaned['nav_sub'] = raw_data.get("navSub") or 0.0
    cleaned['nav_red'] = raw_data.get("navRed") or 0.0
    cleaned['net_asset'] = raw_data.get("netAsset") or 0.0
    cleaned['units'] = raw_data.get("units") or 0.0
    
    # 3. Text Normalization (حذف فاصله‌های اضافی و هندل کردن رشته‌های خالی)
    cleaned['name'] = str(raw_data.get("mfName") or "نامشخص").strip()
    cleaned['manager'] = str(raw_data.get("manager") or "نامشخص").strip()
    
    # 4. Outlier Handling / Constraints
    # درصد دارایی‌ها نباید کمتر از صفر یا بیشتر از ۱۰۰ باشد
    def clip_percentage(val):
        v = float(val or 0.0)
        return max(0.0, min(100.0, v))
        
    cleaned['portfolio_stock'] = clip_percentage(raw_data.get("portfolioStock"))
    cleaned['portfolio_bond'] = clip_percentage(raw_data.get("portfolioBond"))
    cleaned['portfolio_deposit'] = clip_percentage(raw_data.get("portfolioDeposit"))
    
    # 5. Financial Returns (بازدهی‌ها می‌توانند منفی باشند)
    cleaned['day1_return'] = float(raw_data.get("day1Return") or 0.0)
    cleaned['day7_return'] = float(raw_data.get("day7Return") or 0.0)
    cleaned['day30_return'] = float(raw_data.get("day30Return") or 0.0)
    cleaned['day90_return'] = float(raw_data.get("day90Return") or 0.0)
    cleaned['day180_return'] = float(raw_data.get("day180Return") or 0.0)
    cleaned['day365_return'] = float(raw_data.get("day365Return") or 0.0)

    return cleaned