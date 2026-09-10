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
"""
import pytest
from sqlalchemy.orm import Session

from core.models import ETFMarket, ETFMarketHistory, Fund
from services import tasks


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


def _run(monkeypatch, db_session, items, provider=None):
    provider = provider or {}
    monkeypatch.setattr(tasks, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(
        tasks.market_provider, "fetch_live_etf_prices", lambda: items
    )
    monkeypatch.setattr(
        tasks.market_provider,
        "fetch_etf_instrument_info",
        provider.get("instrument_info", lambda ins_code: {"nav": 1000.0}),
    )
    monkeypatch.setattr(
        tasks.market_provider,
        "fetch_etf_nav",
        provider.get(
            "nav", lambda ins_code: {"pRedTran": 1010.0, "pSubTran": 990.0}
        ),
    )
    monkeypatch.setattr(
        tasks.market_provider,
        "fetch_instrument_identity",
        provider.get(
            "identity",
            lambda ins_code: {
                "symbol": "آرامش",
                "sector": "صندوق قابل معامله",
                "subSector": "ETF",
                "market": "بورس",
                "status": "A",
            },
        ),
    )
    tasks.update_etf_market_data()


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
            assert row.sector == "صندوق قابل معامله"

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
            provider={
                "instrument_info": lambda ins_code: None,
                "nav": lambda ins_code: None,
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
        info_calls = []
        nav_calls = []

        _run(
            monkeypatch,
            db_session,
            [_etf_item(nav=None)],
            provider={
                "instrument_info": (
                    lambda ins_code: info_calls.append(ins_code)
                    or {"nav": 950.0}
                ),
                # رکورد pRedTran/pSubTran دارد — endpoint صدور/ابطال نباید صدا زده شود
                "nav": (
                    lambda ins_code: nav_calls.append(ins_code) or {}
                ),
            },
        )

        db = _fresh(db_session)
        try:
            assert info_calls == ["1000"]
            assert nav_calls == []

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
        info_calls = []

        _run(
            monkeypatch,
            db_session,
            [_etf_item(p_red=None, p_sub=None)],
            provider={
                # nav موجود است — endpoint هویت ابزار نباید صدا زده شود
                "instrument_info": (
                    lambda ins_code: info_calls.append(ins_code)
                    or {"nav": 1000.0}
                ),
            },
        )

        db = _fresh(db_session)
        try:
            assert info_calls == []

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

        identity_calls = []
        _run(
            monkeypatch,
            db_session,
            [_etf_item()],
            provider={
                "identity": (
                    lambda ins_code: identity_calls.append(ins_code) or {}
                ),
            },
        )

        assert identity_calls == []

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
