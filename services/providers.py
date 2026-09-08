import logging
import time
import requests

logger = logging.getLogger(__name__)


class TSETMCProvider:

    def __init__(self):
        self.base_url = "https://cdn.tsetmc.com/api"

        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 "
                "(Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 "
                "(KHTML, like Gecko) "
                "Chrome/120.0 Safari/537.36"
            ),
            "Accept": "application/json",
        }

        self.timeout = (5, 30)
        self.max_retries = 3

    def _get_json(self, url: str):
        for attempt in range(1, self.max_retries + 1):

            try:
                response = requests.get(
                    url,
                    headers=self.headers,
                    timeout=self.timeout,
                )

                response.raise_for_status()

                return response.json()

            except requests.RequestException as exc:

                logger.warning(
                    "TSETMC request failed "
                    "(attempt %s/%s): %s",
                    attempt,
                    self.max_retries,
                    exc,
                )

                if attempt < self.max_retries:
                    time.sleep(2 ** (attempt - 1))

        return None

    def fetch_funds_by_type(self, fund_type: int) -> list:

        url = f"{self.base_url}/Fund/GetFunds/{fund_type}"

        data = self._get_json(url)

        if not data:
            return []

        return data.get("funds", [])

    def fetch_live_etf_prices(self) -> list:

        results = []

        for flow in [1, 2]:

            url = (
                f"{self.base_url}/ClosingPrice/"
                f"GetTradeTop/ETF/{flow}/9999"
            )

            data = self._get_json(url)

            if not data:
                continue

            results.extend(
                data.get("tradeTop", [])
            )

        return results

    def fetch_fund_history_detail(self, reg_no: int) -> list:
            """گرفتن تاریخچه 90 روزه یک صندوق (Bootstrap)"""
            # آدرس درست بر اساس مستندات TSETMC
            url = f"{self.base_url}/Fund/GetFundInDetail/{reg_no}"
            
            # لاجیک Retry ساده برای جلوگیری از ارورهای تایم‌اوت موقت بورس
            for attempt in range(3):
                try:
                    response = requests.get(url, headers=self.headers, timeout=10)
                    response.raise_for_status()
                    
                    # استخراج دیتای صندوق
                    data = response.json().get("fund", {})
                    
                    # بر اساس خروجی بورس، آرایه تاریخچه داخل کلید fundProfits است
                    history = data.get("fundProfits", [])
                    
                    # اگر با موفقیت گرفت، از حلقه خارج شو و دیتا را برگردان
                    return history
                    
                except requests.exceptions.RequestException as e:
                    logger.warning(f"TSETMC request failed (attempt {attempt+1}/3): {e}")
                    if attempt == 2:  # اگر بار سوم هم خطا داد
                        return []
            return []