"""Regression tests for the live fund sync pipeline (services/fund_sync.py).

The live pipeline runs every minute for equity funds and is the task's core
path. These tests pin its contract:

- clean records are stored (funds + fund_histories) and SyncStatus says healthy
- a critical cross-field violation quarantines the record (nothing stored,
  issue recorded, failure counted)
- a warning (abnormal NAV move) is recorded but the data is kept
- per-item failures (garbage dates, missing identity) fail only that item
- an empty provider response is safe and still writes SyncStatus

The FK-enabled engine at the bottom guards the audit-table contract: the
quarantined fund is deliberately NOT in ``funds``, so ``data_quality_issues``
must be able to record the issue without a foreign key to ``funds``. In
Postgres that FK made the whole live cycle roll back.
"""
from datetime import datetime

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from core.database import Base
from core.models import DataQualityIssue, Fund, FundHistory, SyncStatus
from services import fund_sync


def _item(
    reg_no,
    nav=1000.0,
    units=1_000_000.0,
    net_asset=1_000_000_000.0,
    record_date="2026-09-10T12:00:00",
    **overrides,
):
    """یک رکورد سالم از پاسخ GetFunds — nav×units = net_asset تا cross-field تمیز بماند."""
    item = {
        "regNo": reg_no,
        "mfName": f"Fund {reg_no}",
        "manager": "مدیر صندوق",
        "navStat": nav,
        "navSub": 990.0,
        "navRed": 1010.0,
        "netAsset": net_asset,
        "units": units,
        "recordDate": record_date,
        "portfolioStock": 100,
        "portfolioBond": 0,
        "portfolioCash": 0,
        "day1Return": 0.1,
        "day7Return": 0.5,
        "day30Return": 2.0,
        "day90Return": 6.0,
        "day180Return": 12.0,
        "day365Return": 25.0,
    }
    item.update(overrides)
    return item


def _run(monkeypatch, db_session, items_by_type):
    monkeypatch.setattr(fund_sync, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(fund_sync, "invalidate_dashboard_cache", lambda: None)
    monkeypatch.setattr(
        fund_sync.provider,
        "fetch_funds_by_type",
        lambda f_type: items_by_type.get(f_type, []),
    )
    fund_sync.sync_funds_pipeline(fund_types=sorted(items_by_type))


def _fresh(db_session) -> Session:
    return Session(bind=db_session.get_bind())


def _status(db) -> SyncStatus:
    return (
        db.query(SyncStatus)
        .filter(SyncStatus.job_name == "fund_sync")
        .first()
    )


class TestCleanRecords:
    def test_clean_record_is_stored(self, db_session, monkeypatch):
        _run(monkeypatch, db_session, {6: [_item(101)]})

        db = _fresh(db_session)
        try:
            fund = db.query(Fund).filter(Fund.reg_no == 101).first()
            assert fund is not None
            assert fund.nav_stat == 1000.0
            assert fund.fund_type == 6

            history = (
                db.query(FundHistory)
                .filter(FundHistory.fund_reg_no == 101)
                .all()
            )
            assert len(history) == 1
            assert history[0].observed_at == datetime(2026, 9, 10, 12, 0)

            assert db.query(DataQualityIssue).count() == 0

            status = _status(db)
            assert status.status == "healthy"
            assert status.valid_count == 1
            assert status.failed_count == 0
            assert status.expected_count == 1
            assert status.received_count == 1
            assert status.error_message is None
            assert status.quality_score == 100.0
        finally:
            db.close()

    def test_missing_record_date_falls_back_to_sync_time(
        self, db_session, monkeypatch
    ):
        _run(monkeypatch, db_session, {6: [_item(102, record_date=None)]})

        db = _fresh(db_session)
        try:
            history = (
                db.query(FundHistory)
                .filter(FundHistory.fund_reg_no == 102)
                .first()
            )
            assert history is not None
            assert history.observed_at is not None
        finally:
            db.close()


class TestQuarantine:
    def test_cross_field_violation_is_quarantined(
        self, db_session, monkeypatch
    ):
        # nav×units = 1e3×5e5 = 5e8 در برابر AUM=1e9 → خطای ۵۰٪ → بحرانی
        _run(monkeypatch, db_session, {6: [_item(201, units=500_000.0)]})

        db = _fresh(db_session)
        try:
            # قرنطینه یعنی هیچ داده‌ای ذخیره نمی‌شود
            assert db.query(Fund).filter(Fund.reg_no == 201).count() == 0
            assert (
                db.query(FundHistory)
                .filter(FundHistory.fund_reg_no == 201)
                .count()
                == 0
            )

            issue = (
                db.query(DataQualityIssue)
                .filter(DataQualityIssue.fund_reg_no == 201)
                .first()
            )
            assert issue is not None
            assert issue.rule == "cross_field"
            assert issue.severity == "critical"

            status = _status(db)
            assert status.status == "partial"
            assert status.failed_count == 1
            assert status.valid_count == 0
            assert "funds failed" in status.error_message
        finally:
            db.close()

    def test_quarantine_does_not_block_other_funds(
        self, db_session, monkeypatch
    ):
        _run(
            monkeypatch,
            db_session,
            {6: [_item(301, units=500_000.0), _item(302)]},
        )

        db = _fresh(db_session)
        try:
            assert db.query(Fund).filter(Fund.reg_no == 302).count() == 1
            assert (
                db.query(FundHistory)
                .filter(FundHistory.fund_reg_no == 302)
                .count()
                == 1
            )
            assert (
                db.query(DataQualityIssue)
                .filter(DataQualityIssue.fund_reg_no == 301)
                .count()
                == 1
            )

            status = _status(db)
            assert status.status == "partial"
            assert status.valid_count == 1
            assert status.failed_count == 1
        finally:
            db.close()


class TestWarnings:
    def test_abnormal_nav_move_is_flagged_but_stored(
        self, db_session, monkeypatch
    ):
        # صندوق از چرخه قبل nav=1000 دارد؛ رکورد جدید 1300 → حرکت ۳۰٪
        db_session.add(
            Fund(reg_no=401, name="Fund 401", fund_type=6, nav_stat=1000.0)
        )
        db_session.commit()

        _run(
            monkeypatch,
            db_session,
            {6: [_item(401, nav=1300.0, net_asset=1_300_000_000.0)]},
        )

        db = _fresh(db_session)
        try:
            fund = db.query(Fund).filter(Fund.reg_no == 401).first()
            assert fund.nav_stat == 1300.0  # داده نگهداری شد

            history = (
                db.query(FundHistory)
                .filter(FundHistory.fund_reg_no == 401)
                .all()
            )
            assert len(history) == 1

            issue = (
                db.query(DataQualityIssue)
                .filter(DataQualityIssue.fund_reg_no == 401)
                .first()
            )
            assert issue is not None
            assert issue.rule == "nav_move"
            assert issue.severity == "warning"

            status = _status(db)
            assert status.status == "healthy"  # هشدار شکست نیست
            assert status.failed_count == 0
            assert status.valid_count == 1
        finally:
            db.close()


class TestFailureIsolation:
    def test_garbage_record_date_fails_only_that_item(
        self, db_session, monkeypatch
    ):
        _run(
            monkeypatch,
            db_session,
            {6: [_item(501, record_date="not-a-date"), _item(502)]},
        )

        db = _fresh(db_session)
        try:
            assert db.query(Fund).filter(Fund.reg_no == 501).count() == 0
            assert db.query(Fund).filter(Fund.reg_no == 502).count() == 1

            status = _status(db)
            assert status.status == "partial"
            assert status.valid_count == 1
            assert status.failed_count == 1
        finally:
            db.close()

    def test_missing_reg_no_fails_only_that_item(
        self, db_session, monkeypatch
    ):
        _run(monkeypatch, db_session, {6: [dict(_item(601), regNo=None)]})

        db = _fresh(db_session)
        try:
            assert db.query(Fund).count() == 0

            status = _status(db)
            assert status.status == "partial"
            assert status.failed_count == 1
            assert status.valid_count == 0
        finally:
            db.close()


class TestEmptyProvider:
    def test_empty_response_is_safe_and_writes_status(
        self, db_session, monkeypatch
    ):
        _run(monkeypatch, db_session, {6: []})

        db = _fresh(db_session)
        try:
            assert db.query(Fund).count() == 0

            status = _status(db)
            assert status is not None
            assert status.status == "healthy"
            assert status.expected_count == 0
            assert status.failed_count == 0
            assert status.quality_score == 0.0
        finally:
            db.close()


class TestAuditTableNeedsNoFundRow:
    """قرنطینه یعنی صندوق در funds ذخیره نمی‌شود — ولی تخلف باید ثبت شود.

    موتور SQLite این کلاس با PRAGMA foreign_keys=ON ساخته می‌شود تا
    قرارداد واقعی Postgres (یکپارچگی ارجاعی) شبیه‌سازی شود. اگر کسی
    دوباره ForeignKey به funds روی data_quality_issues اضافه کند،
    این تست شکست می‌خورد — همان طور که در Postgres کل چرخه را rollback
    می‌کرد.
    """

    @pytest.fixture(scope="class")
    def fk_session_factory(self):
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )

        @event.listens_for(engine, "connect")
        def _enable_fk(dbapi_connection, _record):
            dbapi_connection.execute("PRAGMA foreign_keys=ON")

        Base.metadata.create_all(bind=engine)
        try:
            yield sessionmaker(autocommit=False, autoflush=False, bind=engine)
        finally:
            Base.metadata.drop_all(bind=engine)
            engine.dispose()

    def test_quarantined_new_fund_issue_recorded_without_fk_violation(
        self, fk_session_factory, monkeypatch
    ):
        monkeypatch.setattr(fund_sync, "SessionLocal", fk_session_factory)
        monkeypatch.setattr(
            fund_sync, "invalidate_dashboard_cache", lambda: None
        )
        monkeypatch.setattr(
            fund_sync.provider,
            "fetch_funds_by_type",
            lambda f_type: [_item(701, units=500_000.0), _item(702)],
        )

        fund_sync.sync_funds_pipeline(fund_types=[6])

        db = fk_session_factory()
        try:
            # صندوق سالم ذخیره شد — یعنی خطای ممیزی کل چرخه را برنگردانده
            assert db.query(Fund).count() == 1
            assert db.query(Fund).filter(Fund.reg_no == 702).count() == 1

            issue = (
                db.query(DataQualityIssue)
                .filter(DataQualityIssue.fund_reg_no == 701)
                .first()
            )
            assert issue is not None
            assert issue.severity == "critical"
        finally:
            db.close()
