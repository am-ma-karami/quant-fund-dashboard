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
        except Exception:
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

    def fetch_etf_nav(self, ins_code: str) -> dict:
        """
        دریافت NAV لحظه‌ای ETF.
        مهندسی: این اندپوینت بورس برای بعضی نمادها 500 می‌دهد، پس از
        request_with_retry استفاده نمی‌کنیم تا Circuit Breaker اصلی را آلوده نکنیم.
        """
        url = (
            f"{self.base_url}/Fund/"
            f"GetETFByInsCode/{ins_code}"
        )

        try:
            response = requests.get(
                url,
                headers=self.headers,
                timeout=5,
            )
        except requests.RequestException:
            logger.debug(
                "Timeout/error fetching ETF NAV for %s. Skipping...",
                ins_code,
            )
            return {}

        if response.status_code != 200:
            logger.debug(
                "TSETMC returned %s for ETF NAV %s. Using fallback DB data.",
                response.status_code,
                ins_code,
            )
            return {}

        try:
            data = response.json()
        except ValueError:
            return {}

        if not isinstance(data, dict):
            return {}

        return data.get("etf") or {}

    def fetch_etf_instrument_info(self, ins_code: str) -> dict | None:
        """
        دریافت اطلاعات ابزار شامل NAV از API Instrument Info.
        مهندسی: این اندپوینت هم ناپایدار است و از request_with_retry
        استفاده نمی‌کنیم تا Circuit Breaker اصلی را آلوده نکنیم.
        """
        url = (
            f"{self.base_url}/Instrument/"
            f"GetInstrumentInfo/{ins_code}"
        )

        try:
            response = requests.get(
                url,
                headers=self.headers,
                timeout=5,
            )
        except requests.RequestException:
            logger.debug(
                "Timeout/error fetching ETF instrument info for %s. Skipping...",
                ins_code,
            )
            return None

        if response.status_code != 200:
            logger.debug(
                "TSETMC returned %s for ETF instrument info %s. Skipping...",
                response.status_code,
                ins_code,
            )
            return None

        try:
            data = response.json()
        except ValueError:
            return None

        if not isinstance(data, dict):
            return None

        instrument_info = data.get("instrumentInfo")
        if not isinstance(instrument_info, dict):
            return None

        return {
            "nav": instrument_info.get("nav"),
            "symbol_en": instrument_info.get("lVal18"),
            "name_en": instrument_info.get("lVal30"),
            "symbol": instrument_info.get("lVal18AFC"),
            "ins_code": instrument_info.get("insCode"),
        }

    def fetch_index_history(
        self,
        index_code: str,
    ) -> list:
        url = (
            f"{self.base_url}/Index/"
            f"GetIndexB2History/{index_code}"
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
                "Failed to fetch index history %s",
                index_code,
            )
            return []

        if not isinstance(data, dict):
            return []

        return data.get("indexB2", [])

    def fetch_instrument_identity(
        self,
        ins_code: str,
    ) -> dict | None:
        url = (
            f"{self.base_url}/Instrument/"
            f"GetInstrumentIdentity/{ins_code}"
        )

        try:
            response = requests.get(
                url,
                headers=self.headers,
                timeout=5,
            )
        except requests.RequestException:
            logger.debug(
                "Timeout/error fetching instrument identity %s. Skipping...",
                ins_code,
            )
            return None

        if response.status_code != 200:
            logger.debug(
                "TSETMC returned %s for instrument identity %s. Skipping...",
                response.status_code,
                ins_code,
            )
            return None

        try:
            data = response.json()
        except ValueError:
            return None

        if not isinstance(data, dict):
            return None

        return data.get("instrumentIdentity")

    def fetch_instrument_state(
        self,
        ins_code: str,
        date_str: str,
    ) -> dict | None:
        url = (
            f"{self.base_url}/MarketData/"
            f"GetInstrumentState/{ins_code}/{date_str}"
        )

        try:
            response = requests.get(
                url,
                headers=self.headers,
                timeout=5,
            )
        except requests.RequestException:
            logger.debug(
                "Timeout/error fetching instrument state %s. Skipping...",
                ins_code,
            )
            return None

        if response.status_code != 200:
            logger.debug(
                "TSETMC returned %s for instrument state %s. Skipping...",
                response.status_code,
                ins_code,
            )
            return None

        try:
            data = response.json()
        except ValueError:
            return None

        if not isinstance(data, dict):
            return None

        return data.get("instrumentState")

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
        except requests.RequestException:
            logger.exception("Failed to fetch history for fund %s", reg_no)
            return []

        history = data.get("fund", {}).get("stats", [])

        logger.info("Fund %s fetched %s history records", reg_no, len(history))

        return history

