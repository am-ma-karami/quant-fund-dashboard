import requests
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
}

def fetch_funds_by_type(fund_type: int):
    """دریافت لیست صندوق‌ها بر اساس نوع (۴ تا ۱۷)"""
    url = f"https://cdn.tsetmc.com/api/Fund/GetFunds/{fund_type}"
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        data = response.json()
        return data.get("funds", [])
    except Exception as e:
        logger.error(f"Error fetching funds for type {fund_type}: {e}")
        return []

def fetch_live_etf_prices():
    """دریافت قیمت‌های لحظه‌ای تمام ETFها از روی تابلو به صورت یکجا"""
    url = "https://cdn.tsetmc.com/api/ClosingPrice/GetTradeTop/ETF/0/9999"
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        data = response.json()
        return data.get("tradeTop", [])
    except Exception as e:
        logger.error(f"Error fetching live ETF prices: {e}")
        return []