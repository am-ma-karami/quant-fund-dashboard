"""Tests for the live ETF sync task (services/tasks.py update_etf_market_data).

The ETF board runs every minute and is the task's second live path. These
tests pin its contract:

- a complete board row is stored with premium computed (percent scale)
- missing NAV is enriched from the instrument-info endpoint (network phase)
- missing redemption/subscription prices are enriched from the NAV endpoint
- an ETF with no NAV anywhere is still stored, with a NULL premium
- an empty board is safe
- fuzzy name matching links an unmapped fund to its ETF
- instrument identity is fetched only when the stored sector is unknown
  (guards the two-phase structure: network calls must not happen inside
  the write transaction)

Since the async migration, the network phase is exercised against a real
``httpx.AsyncClient`` backed by ``httpx.MockTransport`` — the provider
methods' parsing and the ``asyncio.gather`` fan-out run exactly as in
production, and two further properties are proven:

- enrichment requests across items run concurrently (wall-clock proof)
- a network failure for one ETF isolates that item only
"""
import asyncio
import functools
import time

import httpx
import pytest
from sqlalchemy.orm import Session

from core.models import ETFMarket, ETFMarketHistory, Fund
from services import tasks


# شکل واقعی پاسخ TSETMC — sector و subSector شیءهای تودرتو هستند، نه
# رشته. این همان قراردادی است که در اجرای واقعی «can't adapt type 'dict'»
# میداد؛ نرمال‌سازی باید در provider انجام شود و این تست آن را قفل می‌کند.
DEFAULT_IDENTITY = {
    "sector": {"lSecVal": "صندوق قابل معامله"},
    "subSector": {"lSoSecVal": "ETF"},
    "lVal18AFC": "آرامش",
    "lVal30": "ETF آرامش",
    "cgrValCotTitle": "بازار صندوق های قابل معامله",
}


def _etf_item(
    ins_code="1000",
    symbol="آرامش",
    name="ETF آرامش",
    last_price=1050.0,
    nav=1000.0,
    p_red=1010.0,
    p_sub=990.0,
    **overrides,
):
    item = {
        "insCode": ins_code,
        "instrument": {"lVal18AFC": symbol, "lVal30": name},
        "pDrCotVal": last_price,
        "pClosing": 1040.0,
        "priceChange": 10.0,
        "zTotTran": 100,
        "qTotTran5J": 500000,
        "qTotCap": 525000000,
        "priceMin": 1030.0,
        "priceMax": 1060.0,
        "priceFirst": 1035.0,
        "priceYesterday": 1040.0,
        "nav": nav,
        "pRedTran": p_red,
        "pSubTran": p_sub,
    }
    item.update(overrides)
    return item


def _build_handler(record: dict, responses: dict):
    """مسیریاب MockTransport بر اساس زیررشته مسیر — همان قرارداد provider واقعی."""

    async def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        ins_code = path.rstrip("/").split("/")[-1]

        if "GetETFByInsCode" in path:
            record["nav"].append(ins_code)
            body = responses.get("etf", {"pRedTran": 1010.0, "pSubTran": 990.0})
            return httpx.Response(200, json={"etf": body})
        if "GetInstrumentInfo" in path:
            record["info"].append(ins_code)
            body = responses.get("instrument_info", {"nav": 1000.0})
            return httpx.Response(200, json={"instrumentInfo": body})
        if "GetInstrumentIdentity" in path:
            record["identity"].append(ins_code)
            body = responses.get("identity", DEFAULT_IDENTITY)
            return httpx.Response(200, json={"instrumentIdentity": body})
        return httpx.Response(404, json={})

    return handler


def _run(monkeypatch, db_session, items, responses=None, wrap=None):
    """اجرای یک چرخه سینک ETF روی MockTransport و برگرداندن درخواست‌های ثبت‌شده.

    ``wrap`` یک پوشش اختیاری روی مسیریاب است (مثلاً برای تزریق تأخیر یا
    خطای شبکه) — همان نقطه تزریق‌پذیری که در تولید هم وجود دارد.
    """
    responses = responses or {}
    record = {"info": [], "nav": [], "identity": []}
    base = _build_handler(record, responses)
    if wrap is not None:
        base = functools.partial(wrap, base)

    transport = httpx.MockTransport(base)
    monkeypatch.setattr(tasks, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(
        tasks.market_provider, "fetch_live_etf_prices", lambda: items
    )
    monkeypatch.setattr(
        tasks,
        "_new_async_client",
        lambda: httpx.AsyncClient(
            transport=transport,
            headers=tasks.market_provider.headers,
            timeout=httpx.Timeout(5.0),
        ),
    )
    asyncio.run(tasks.update_etf_market_data())
    return record


def _fresh(db_session) -> Session:
    return Session(bind=db_session.get_bind())


class TestBoardStorage:
    def test_complete_row_is_stored_with_premium(self, db_session, monkeypatch):
        _run(monkeypatch, db_session, [_etf_item()])

        db = _fresh(db_session)
        try:
            row = (
                db.query(ETFMarket)
                .filter(ETFMarket.ins_code == "1000")
                .first()
            )
            assert row is not None
            assert row.last_price == 1050.0
            assert row.nav == 1000.0
            # (1050/1000 − 1) × 100 — مقایسه شناور با approx
            assert row.premium_discount == pytest.approx(5.0)
            assert row.symbol == "آرامش"
            # قرارداد نرمال‌شده: رشته‌ها از شیءهای تودرتوی منبع استخراج شده‌اند
            assert row.sector == "صندوق قابل معامله"
            assert row.subsector == "ETF"
            assert row.market == "بازار صندوق های قابل معامله"

            history = (
                db.query(ETFMarketHistory)
                .filter(ETFMarketHistory.ins_code == "1000")
                .all()
            )
            assert len(history) == 1
            assert history[0].premium_discount == pytest.approx(5.0)
            assert history[0].observed_at is not None
        finally:
            db.close()

    def test_empty_board_is_safe(self, db_session, monkeypatch):
        _run(monkeypatch, db_session, [])

        db = _fresh(db_session)
        try:
            assert db.query(ETFMarket).count() == 0
            assert db.query(ETFMarketHistory).count() == 0
        finally:
            db.close()

    def test_missing_everything_stores_null_premium(
        self, db_session, monkeypatch
    ):
        _run(
            monkeypatch,
            db_session,
            [_etf_item(nav=None, p_red=None, p_sub=None)],
            responses={
                "instrument_info": None,
                "etf": {},
            },
        )

        db = _fresh(db_session)
        try:
            row = (
                db.query(ETFMarket)
                .filter(ETFMarket.ins_code == "1000")
                .first()
            )
            assert row is not None
            assert row.nav is None
            assert row.premium_discount is None
        finally:
            db.close()


class TestEnrichment:
    def test_nav_enriched_from_instrument_info(
        self, db_session, monkeypatch
    ):
        record = _run(
            monkeypatch,
            db_session,
            [_etf_item(nav=None)],
            responses={"instrument_info": {"nav": 950.0}},
        )

        db = _fresh(db_session)
        try:
            assert record["info"] == ["1000"]
            # رکورد pRedTran/pSubTran دارد — endpoint صدور/ابطال نباید صدا زده شود
            assert record["nav"] == []

            row = (
                db.query(ETFMarket)
                .filter(ETFMarket.ins_code == "1000")
                .first()
            )
            assert row.nav == 950.0
            assert round(row.premium_discount, 2) == 10.53
        finally:
            db.close()

    def test_redemption_prices_enriched_from_nav_endpoint(
        self, db_session, monkeypatch
    ):
        record = _run(
            monkeypatch,
            db_session,
            [_etf_item(p_red=None, p_sub=None)],
        )

        db = _fresh(db_session)
        try:
            # nav موجود است — endpoint هویت ابزار نباید صدا زده شود
            assert record["info"] == []
            assert record["nav"] == ["1000"]

            row = (
                db.query(ETFMarket)
                .filter(ETFMarket.ins_code == "1000")
                .first()
            )
            assert row.nav_red == 1010.0
            assert row.nav_sub == 990.0
        finally:
            db.close()


class TestIdentityAndMapping:
    def test_identity_fetched_only_when_sector_unknown(
        self, db_session, monkeypatch
    ):
        # صندوق از چرخه قبل sector دارد — درخواست هویت نباید تکرار شود
        db_session.add(
            ETFMarket(
                ins_code="1000", symbol="آرامش", name="ETF آرامش", sector="دارد"
            )
        )
        db_session.commit()

        record = _run(monkeypatch, db_session, [_etf_item()])

        assert record["identity"] == []

    def test_fuzzy_mapping_links_unmapped_fund_to_etf(
        self, db_session, monkeypatch
    ):
        db_session.add(
            Fund(
                reg_no=111,
                name="صندوق سرمایه گذاری در سهام آرامش",
                fund_type=6,
            )
        )
        db_session.commit()

        _run(
            monkeypatch,
            db_session,
            [_etf_item(ins_code="1000", symbol="آرامش")],
        )

        db = _fresh(db_session)
        try:
            fund = db.query(Fund).filter(Fund.reg_no == 111).first()
            assert fund.ins_code == "1000"
            assert fund.is_etf is True
        finally:
            db.close()


class TestConcurrency:
    def test_enrichment_requests_run_concurrently(self, db_session, monkeypatch):
        """اثبات همزمانی: ۸ ردیف × ۳ درخواست با تأخیر ۰٫۲ ثانیه‌ای.

        اجرای ترتیبی ≈ ۸ × ۳ × ۰٫۲ = ۴٫۸ ثانیه؛ اجرای همزمان ≈ ۰٫۲ ثانیه.
        آستانه ۱٫۰ ثانیه بین این دو فاصله امن می‌گذارد.
        """

        async def slow(base, request):
            await asyncio.sleep(0.2)
            return await base(request)

        items = [
            _etf_item(ins_code=f"100{i}", nav=None, p_red=None, p_sub=None)
            for i in range(8)
        ]

        start = time.monotonic()
        record = _run(monkeypatch, db_session, items, wrap=slow)
        elapsed = time.monotonic() - start

        assert elapsed < 1.0, (
            f"چرخه {elapsed:.2f} ثانیه طول کشید — درخواست‌های تکمیلی همزمان اجرا نشدند"
        )
        # هر ۸ ردیف هر ۳ درخواست تکمیلی خود را کامل دریافت کردند
        assert len(record["info"]) == 8
        assert len(record["nav"]) == 8
        assert len(record["identity"]) == 8


class TestFailureIsolation:
    def test_network_failure_for_one_etf_isolates_that_item(
        self, db_session, monkeypatch
    ):
        """شکست شبکه برای یک نماد، فقط همان ردیف را از غنی‌سازی محروم می‌کند.

        ردیف خراب همچنان (با همان داده تابلوی bulk و پریمیوم NULL) ذخیره
        می‌شود — چرخه و بقیه ردیف‌ها سالم می‌مانند.
        """

        async def flaky(base, request):
            if "2000" in request.url.path:
                raise httpx.ConnectError(
                    "provider unreachable", request=request
                )
            return await base(request)

        _run(
            monkeypatch,
            db_session,
            [
                _etf_item(ins_code="1000"),
                _etf_item(ins_code="2000", nav=None, p_red=None, p_sub=None),
                _etf_item(ins_code="3000"),
            ],
            wrap=flaky,
        )

        db = _fresh(db_session)
        try:
            rows = db.query(ETFMarket).order_by(ETFMarket.ins_code).all()
            assert [row.ins_code for row in rows] == ["1000", "2000", "3000"]

            broken = (
                db.query(ETFMarket)
                .filter(ETFMarket.ins_code == "2000")
                .first()
            )
            assert broken is not None
            assert broken.last_price == 1050.0
            assert broken.nav is None
            assert broken.premium_discount is None

            healthy = (
                db.query(ETFMarket)
                .filter(ETFMarket.ins_code == "3000")
                .first()
            )
            assert healthy.premium_discount == pytest.approx(5.0)
        finally:
            db.close()
