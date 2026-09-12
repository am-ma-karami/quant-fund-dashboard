"""Regression tests for the history backfill pipeline.

These cover the bug where TSETMC ISO ``recordDate`` values
(``"2012-09-23T00:00:00"``) were rejected by an 8-digit-only parser,
so the backfill silently inserted zero rows and re-downloaded the
same funds forever.
"""
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from core.models import (
    Fund,
    FundHistory,
    ETFMarket,
    ETFMarketHistory,
    HistoryBackfillState,
)
from core.repositories import iran_time
from services import history_bootstrap as hb


def _iso_dates(days: int, end=None) -> list[str]:
    end = end or iran_time()
    return [
        (end - timedelta(days=i)).strftime("%Y-%m-%dT00:00:00")
        for i in range(days)
    ]


class TestParseTsetmcDate:
    def test_iso_string(self):
        assert hb.parse_tsetmc_date("2012-09-23T00:00:00") == datetime(2012, 9, 23)

    def test_iso_string_with_time(self):
        assert hb.parse_tsetmc_date("2026-09-08T12:34:56") == datetime(
            2026, 9, 8, 12, 34, 56
        )

    def test_eight_digit_string(self):
        assert hb.parse_tsetmc_date("20260908") == datetime(2026, 9, 8)

    def test_eight_digit_int(self):
        assert hb.parse_tsetmc_date(20260908) == datetime(2026, 9, 8)

    def test_none(self):
        assert hb.parse_tsetmc_date(None) is None

    def test_empty_string(self):
        assert hb.parse_tsetmc_date("") is None

    def test_garbage(self):
        assert hb.parse_tsetmc_date("not-a-date") is None

    def test_iso_string_returns_naive(self):
        parsed = hb.parse_tsetmc_date("2026-09-08T00:00:00+03:30")
        assert parsed is not None
        assert parsed.tzinfo is None


class TestBackfillSingleFund:
    def _patch_session(self, monkeypatch, db_session):
        monkeypatch.setattr(hb, "SessionLocal", lambda: db_session)

    def _add_fund(self, db, reg_no, is_etf=False, ins_code=None):
        fund = Fund(reg_no=reg_no, name=f"Fund {reg_no}", fund_type=6)
        if is_etf:
            fund.is_etf = True
            fund.ins_code = ins_code or str(reg_no)
        db.add(fund)
        db.commit()
        return fund

    def _fresh_session(self, db_session):
        return Session(bind=db_session.get_bind())

    def test_backfill_inserts_iso_history_and_marks_checked(
        self, db_session, monkeypatch
    ):
        self._patch_session(monkeypatch, db_session)
        self._add_fund(db_session, 123)

        records = [
            {"recordDate": d, "navStat": float(100 + i), "netAsset": 1e9}
            for i, d in enumerate(_iso_dates(20))
        ]
        monkeypatch.setattr(
            hb.provider,
            "fetch_fund_history_detail",
            lambda reg_no: records,
        )

        hb.backfill_single_fund()

        db = self._fresh_session(db_session)
        try:
            rows = (
                db.query(FundHistory)
                .filter(FundHistory.fund_reg_no == 123)
                .count()
            )
            assert rows == 20

            state = db.get(HistoryBackfillState, 123)
            assert state is not None
            assert state.checked_at is not None
            assert state.source_count == 20
        finally:
            db.close()

    def test_source_count_records_short_source(self, db_session, monkeypatch):
        """منبع با کمتر از ۹۰ رکورد: تعداد واقعی منبع باید ثبت شود."""
        self._patch_session(monkeypatch, db_session)
        self._add_fund(db_session, 555)

        monkeypatch.setattr(
            hb.provider,
            "fetch_fund_history_detail",
            lambda reg_no: [
                {"recordDate": d, "navStat": 1.0, "netAsset": 1e9}
                for d in _iso_dates(3)
            ],
        )

        hb.backfill_single_fund()

        db = self._fresh_session(db_session)
        try:
            state = db.get(HistoryBackfillState, 555)
            assert state is not None
            assert state.source_count == 3
        finally:
            db.close()

    def test_failed_fetch_preserves_previous_source_count(self, db_session, monkeypatch):
        """شکست دریافت نباید شواهد تلاش موفق قبلی را پاک کند."""
        self._patch_session(monkeypatch, db_session)
        self._add_fund(db_session, 666)
        stale = iran_time() - timedelta(hours=24)
        db_session.add(
            HistoryBackfillState(
                fund_reg_no=666,
                checked_at=stale,
                source_count=5,
            )
        )
        db_session.commit()

        monkeypatch.setattr(
            hb.provider,
            "fetch_fund_history_detail",
            lambda reg_no: None,
        )

        hb.backfill_single_fund()

        db = self._fresh_session(db_session)
        try:
            state = db.get(HistoryBackfillState, 666)
            assert state is not None
            assert state.checked_at > stale
            assert state.source_count == 5
        finally:
            db.close()

    def test_recently_checked_fund_is_skipped(self, db_session, monkeypatch):
        self._patch_session(monkeypatch, db_session)
        self._add_fund(db_session, 456)
        db_session.add(
            HistoryBackfillState(fund_reg_no=456, checked_at=iran_time())
        )
        db_session.commit()

        calls = []
        monkeypatch.setattr(
            hb.provider,
            "fetch_fund_history_detail",
            lambda reg_no: calls.append(reg_no) or [],
        )

        hb.backfill_single_fund()

        assert calls == []

    def test_stale_checked_fund_is_retried(self, db_session, monkeypatch):
        self._patch_session(monkeypatch, db_session)
        self._add_fund(db_session, 789)
        db_session.add(
            HistoryBackfillState(
                fund_reg_no=789,
                checked_at=iran_time() - timedelta(hours=24),
            )
        )
        db_session.commit()

        monkeypatch.setattr(
            hb.provider,
            "fetch_fund_history_detail",
            lambda reg_no: [
                {"recordDate": d, "navStat": 1.0, "netAsset": 1e9}
                for d in _iso_dates(10)
            ],
        )

        hb.backfill_single_fund()

        db = self._fresh_session(db_session)
        try:
            rows = (
                db.query(FundHistory)
                .filter(FundHistory.fund_reg_no == 789)
                .count()
            )
            assert rows == 10
        finally:
            db.close()

    def test_etf_fund_backfills_market_history(self, db_session, monkeypatch):
        self._patch_session(monkeypatch, db_session)
        self._add_fund(db_session, 321, is_etf=True, ins_code="777")
        db_session.add(ETFMarket(ins_code="777"))
        db_session.commit()

        monkeypatch.setattr(
            hb.provider,
            "fetch_fund_history_detail",
            lambda reg_no: [],
        )
        monkeypatch.setattr(
            hb.provider,
            "fetch_etf_history",
            lambda ins_code, limit: [
                {
                    "dEven": int((iran_time() - timedelta(days=i)).strftime("%Y%m%d")),
                    "pDrCotVal": 1000.0 + i,
                    "pClosing": 990.0 + i,
                }
                for i in range(5)
            ],
        )

        hb.backfill_single_fund()

        db = self._fresh_session(db_session)
        try:
            rows = (
                db.query(ETFMarketHistory)
                .filter(ETFMarketHistory.ins_code == "777")
                .count()
            )
            assert rows == 5
        finally:
            db.close()
