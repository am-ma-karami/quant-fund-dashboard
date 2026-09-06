import requests
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
}

def fetch_stock_funds():
    """دریافت لیست تمام صندوق‌های سهامی (نوع ۶)"""
    url = "https://cdn.tsetmc.com/api/Fund/GetFunds/6"
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        data = response.json()
        return data.get("funds", [])
    except Exception as e:
        logger.error(f"Error fetching funds: {e}")
        return []