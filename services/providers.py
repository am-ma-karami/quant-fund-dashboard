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
        # افزایش Timeout برای اینترنت‌های ناپایدار
        self.timeout = 15

    def fetch_funds_by_type(self, fund_type: int) -> list:
        url = f"{self.base_url}/Fund/GetFunds/{fund_type}"
        try:
            response = requests.get(url, headers=self.headers, timeout=self.timeout)
            response.raise_for_status()
            return response.json().get("funds", [])
        except Exception as e:
            logger.warning(f"Provider Warning (fetch_funds_by_type {fund_type}): {e}")
            return []

    def fetch_live_etf_prices(self) -> list:
        """
        برای جلوگیری از ارور 502 در سرور بورس، 
        به جای flow=0، دیتای بورس (1) و فرابورس (2) را جداگانه می‌گیریم و ترکیب می‌کنیم.
        """
        results = []
        # 1: بازار بورس ، 2: بازار فرابورس
        for flow in [1, 2]:
            url = f"{self.base_url}/ClosingPrice/GetTradeTop/ETF/{flow}/9999"
            try:
                response = requests.get(url, headers=self.headers, timeout=self.timeout)
                response.raise_for_status()
                data = response.json().get("tradeTop", [])
                results.extend(data)
            except Exception as e:
                logger.warning(f"Provider Warning (fetch_live_etf_prices flow {flow}): {e}")
                
        return results

    def fetch_fund_history_detail(self, reg_no: int) -> list:
        """گرفتن تاریخچه 90 روزه یک صندوق (Bootstrap)"""
        url = f"{self.base_url}/Fund/GetFundInDetail/{reg_no}"
        try:
            response = requests.get(url, headers=self.headers, timeout=self.timeout)
            response.raise_for_status()
            data = response.json().get("fund", {})
            # بورس تاریخچه را در کلید fundProfits یا مستقیما به عنوان آرایه برمی‌گرداند
            # ساختار دقیق API برای تاریخچه NAV
            history = data.get("fundProfits", []) if isinstance(data, dict) else []
            return history
        except Exception as e:
            logger.warning(f"Provider Warning (fetch_fund_history {reg_no}): {e}")
            return []