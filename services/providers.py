import logging
import time
import requests


logger = logging.getLogger(__name__)


def request_with_retry(
    url: str,
    *,
    headers: dict = None,
    params: dict = None,
    timeout: int = 10,
    retries: int = 3,
):
    last_error = None

    for attempt in range(retries):
        try:
            response = requests.get(
                url,
                headers=headers,
                params=params,
                timeout=timeout,
            )

            response.raise_for_status()

            return response

        except requests.RequestException as exc:
            last_error = exc

            if attempt == retries - 1:
                break

            sleep_time = 2 ** attempt

            time.sleep(sleep_time)

    raise last_error


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

        self.timeout = 10
        self.max_retries = 3

    def fetch_funds_by_type(self, fund_type: int) -> list:

        url = f"{self.base_url}/Fund/GetFunds/{fund_type}"

        try:
            response = request_with_retry(
                url,
                headers=self.headers,
                timeout=self.timeout,
                retries=self.max_retries,
            )
            data = response.json()
        except requests.RequestException:
            logger.exception("Failed to fetch funds by type %s", fund_type)
            return []

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

            try:
                response = request_with_retry(
                    url,
                    headers=self.headers,
                    timeout=self.timeout,
                    retries=self.max_retries,
                )
                data = response.json()
            except requests.RequestException:
                logger.exception("Failed to fetch ETF prices for flow %s", flow)
                continue

            if not data:
                continue

            results.extend(
                data.get("tradeTop", [])
            )

        return results

    def fetch_fund_history_detail(self, reg_no: int) -> list:
        """گرفتن تاریخچه 90 روزه یک صندوق (Bootstrap)"""
        url = f"{self.base_url}/Fund/GetFundInDetail/{reg_no}"

        try:
            response = request_with_retry(
                url,
                headers=self.headers,
                timeout=self.timeout,
                retries=self.max_retries,
            )
            data = response.json().get("fund", {})
        except requests.RequestException:
            logger.exception("Failed to fetch history for fund %s", reg_no)
            return []

        history = data.get("fundProfits", [])

        return history