import logging
import re

logger = logging.getLogger(__name__)


def normalize_fund_name(name: str) -> str:
    if not name:
        return ""
    n = name.replace("ي", "ی").replace("ك", "ک").replace("آ", "ا")
    words_to_remove = [
        "صندوق",
        "سرمایه گذاری",
        "سرمایه",
        "گذاری",
        "در سهام",
        "مختلط",
        "درآمد ثابت",
        "قابل معامله",
        "ETF",
        "س ",
        "س.",
        "اختصاصی",
        "بازارگردانی",
        "جسورانه",
        "پروژه",
        "املاک و مستغلات",
        "بخشی",
        "نوع دوم",
        "مشترک",
        "یکم",
        "د",
        "ب",
        "س",
        "اهرمی",
    ]
    for w in words_to_remove:
        n = n.replace(w, "")
    n = re.sub(r'\s+', '', n)
    n = re.sub(r'[^a-zA-Z0-9ا-ی]', '', n)
    return n


def clean_fund_data(raw_data: dict) -> dict:
    cleaned = {}
    try:
        cleaned['reg_no'] = int(raw_data.get("regNo", 0))
    except Exception:
        cleaned['reg_no'] = 0

    cleaned['nav_stat'] = float(raw_data.get("navStat") or 0.0)
    cleaned['nav_sub'] = float(raw_data.get("navSub") or 0.0)
    cleaned['nav_red'] = float(raw_data.get("navRed") or 0.0)
    cleaned['net_asset'] = float(raw_data.get("netAsset") or 0.0)
    cleaned['units'] = float(raw_data.get("units") or 0.0)
    cleaned['name'] = str(raw_data.get("mfName") or "نامشخص").strip()
    cleaned['manager'] = str(raw_data.get("manager") or "نامشخص").strip()

    stock = float(raw_data.get("portfolioStock") or 0.0)
    bond = float(raw_data.get("portfolioBond") or 0.0)
    cash = max(
        float(raw_data.get("portfolioCash") or 0.0),
        float(raw_data.get("portfolioDeposit") or 0.0),
    )
    other = float(raw_data.get("portfolioOther") or 0.0)

    total_portfolio = stock + bond + cash + other
    if total_portfolio > 0:
        cleaned['portfolio_stock'] = round((stock / total_portfolio) * 100, 2)
        cleaned['portfolio_bond'] = round((bond / total_portfolio) * 100, 2)
        cleaned['portfolio_cash'] = round((cash / total_portfolio) * 100, 2)
        cleaned['portfolio_other'] = round((other / total_portfolio) * 100, 2)
    else:
        cleaned['portfolio_stock'] = 0.0
        cleaned['portfolio_bond'] = 0.0
        cleaned['portfolio_cash'] = 0.0
        cleaned['portfolio_other'] = 0.0

    cleaned['day1_return'] = float(raw_data.get("day1Return") or 0.0)
    cleaned['day7_return'] = float(raw_data.get("day7Return") or 0.0)
    cleaned['day30_return'] = float(raw_data.get("day30Return") or 0.0)
    cleaned['day90_return'] = float(raw_data.get("day90Return") or 0.0)
    cleaned['day180_return'] = float(raw_data.get("day180Return") or 0.0)
    cleaned['day365_return'] = float(raw_data.get("day365Return") or 0.0)

    return cleaned
