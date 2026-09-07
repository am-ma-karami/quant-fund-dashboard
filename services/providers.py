import requests
import logging

logger = logging.getLogger(__name__)

class TSETMCProvider:
    """کلاس پروایدر برای ارتباط با سیستم TSETMC"""
    
    def __init__(self):
        self.base_url = "https://cdn.tsetmc.com/api"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        }
        self.timeout = 10

    def fetch_funds_by_type(self, fund_type: int) -> list:
        url = f"{self.base_url}/Fund/GetFunds/{fund_type}"
        try:
            response = requests.get(url, headers=self.headers, timeout=self.timeout)
            response.raise_for_status()
            return response.json().get("funds", [])
        except Exception as e:
            logger.error(f"Provider Error (fetch_funds_by_type {fund_type}): {e}")
            return []

    def fetch_live_etf_prices(self) -> list:
        url = f"{self.base_url}/ClosingPrice/GetTradeTop/ETF/0/9999"
        try:
            response = requests.get(url, headers=self.headers, timeout=self.timeout)
            response.raise_for_status()
            return response.json().get("tradeTop", [])
        except Exception as e:
            logger.error(f"Provider Error (fetch_live_etf_prices): {e}")
            return []