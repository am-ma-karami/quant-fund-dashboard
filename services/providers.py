import logging
import time
import requests
from threading import Lock


logger = logging.getLogger(__name__)


class CircuitBreaker:
    def __init__(self, failure_threshold: int = 10, cooldown: int = 30):
        self.failure_threshold = failure_threshold
        self.cooldown = cooldown
        self.failures = 0
        self.last_failure_time = 0
        self._lock = Lock()
        self.is_open = False

    def record_success(self):
        with self._lock:
            self.failures = 0
            self.is_open = False

    def record_failure(self):
        with self._lock:
            self.failures += 1
            self.last_failure_time = time.time()
            if self.failures >= self.failure_threshold:
                self.is_open = True
                logger.warning("Circuit breaker OPENED after %s failures", self.failures)

    def can_execute(self) -> bool:
        with self._lock:
            if not self.is_open:
                return True
            if time.time() - self.last_failure_time > self.cooldown:
                self.is_open = False
                self.failures = 0
                logger.info("Circuit breaker CLOSED (cooldown elapsed)")
                return True
            return False


_circuit_breaker = CircuitBreaker(failure_threshold=5, cooldown=60)


def request_with_retry(
    url: str,
    *,
    headers: dict = None,
    params: dict = None,
    timeout: int = 30,
    retries: int = 3,
):
    logger.debug("Circuit breaker state: is_open=%s, failures=%s", _circuit_breaker.is_open, _circuit_breaker.failures)
    if not _circuit_breaker.can_execute():
        logger.warning("Circuit breaker open - skipping request to %s (failures=%s)", url, _circuit_breaker.failures)
        raise requests.RequestException("Circuit breaker open - service unavailable")

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
            _circuit_breaker.record_success()

            return response

        except requests.RequestException as exc:
            last_error = exc
            _circuit_breaker.record_failure()

            logger.warning("Request attempt %s/%s failed for %s: %s (circuit breaker failures=%s)", attempt + 1, retries, url, exc, _circuit_breaker.failures)

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

        self.timeout = 30
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
        """دریافت دیتای کامل بازار ETF از API TradeTop."""
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
                logger.exception(
                    "Failed to fetch ETF prices for flow %s",
                    flow,
                )
                continue

            if not data:
                continue

            results.extend(
                data.get("tradeTop", [])
            )

        return results

    def fetch_etf_nav(self, ins_code: str) -> dict | None:
        """دریافت NAV لحظه‌ای ETF از API اختصاصی."""
        url = (
            f"{self.base_url}/Fund/"
            f"GetETFByInsCode/{ins_code}"
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
            logger.exception(
                "Failed to fetch ETF NAV for %s",
                ins_code,
            )
            return None

        if not isinstance(data, dict):
            return None

        return data.get("etf")

    def fetch_etf_history(
        self,
        ins_code: str,
        days: int = 365,
    ) -> list:
        """دریافت تاریخچه قیمت روزانه ETF."""
        url = (
            f"{self.base_url}/ClosingPrice/"
            f"GetClosingPriceDailyList/"
            f"{ins_code}/{days}"
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
            logger.exception(
                "Failed to fetch ETF history %s",
                ins_code,
            )
            return []

        if not isinstance(data, dict):
            return []

        return data.get("closingPriceDaily", [])

    def fetch_fund_history_detail(self, reg_no: int) -> list:
        """گرفتن تاریخچه صندوق برای bootstrap/backfill."""
        url = f"{self.base_url}/Fund/GetFundInDetail/{reg_no}"

        try:
            response = request_with_retry(
                url,
                headers=self.headers,
                timeout=self.timeout,
                retries=self.max_retries,
            )
            data = response.json()
            logger.info("Fund %s history detail response keys: %s", reg_no, list(data.keys()) if isinstance(data, dict) else type(data))
            if isinstance(data, dict) and "fund" in data:
                fund_obj = data["fund"]
                logger.info("Fund %s fund object keys: %s", reg_no, list(fund_obj.keys()) if isinstance(fund_obj, dict) else type(fund_obj))
                if isinstance(fund_obj, dict) and "stats" in fund_obj:
                    logger.info("Fund %s stats length: %s", reg_no, len(fund_obj["stats"]))
        except requests.RequestException:
            logger.exception("Failed to fetch history for fund %s", reg_no)
            return []

        history = data.get("fund", {}).get("stats", [])

        logger.info("Fund %s fetched %s history records", reg_no, len(history))

        return history
