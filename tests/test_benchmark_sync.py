"""Regression tests for benchmark (TEDPIX) history sync."""
from datetime import timedelta

from sqlalchemy.orm import Session

from core.benchmark import TEHRAN_TOTAL_INDEX
from core.models import BenchmarkHistory
from core.repositories import iran_time
from services import benchmark_sync as bs


def _index_items(days: int) -> list[dict]:
    return [
        {
            "dEven": int(
                (iran_time() - timedelta(days=i)).strftime("%Y%m%d")
            ),
            "xNivInuClMresIbs": 7000000.0 + i,
        }
        for i in range(days)
    ]


class TestBenchmarkSync:
    def _patch_session(self, monkeypatch, db_session):
        monkeypatch.setattr(bs, "SessionLocal", lambda: db_session)

    def _fresh_session(self, db_session):
        return Session(bind=db_session.get_bind())

    def test_first_sync_stores_all_observations(self, db_session, monkeypatch):
        self._patch_session(monkeypatch, db_session)
        monkeypatch.setattr(
            bs.provider,
            "fetch_index_history",
            lambda code: _index_items(5),
        )

        bs.sync_benchmark_history()

        db = self._fresh_session(db_session)
        try:
            rows = db.query(BenchmarkHistory).count()
            assert rows == 5
        finally:
            db.close()

    def test_second_sync_is_incremental(self, db_session, monkeypatch):
        self._patch_session(monkeypatch, db_session)
        monkeypatch.setattr(
            bs.provider,
            "fetch_index_history",
            lambda code: _index_items(5),
        )

        bs.sync_benchmark_history()
        bs.sync_benchmark_history()

        db = self._fresh_session(db_session)
        try:
            rows = db.query(BenchmarkHistory).count()
            assert rows == 5  # no duplicates on re-sync
        finally:
            db.close()

    def test_invalid_observations_are_skipped(self, db_session, monkeypatch):
        self._patch_session(monkeypatch, db_session)
        monkeypatch.setattr(
            bs.provider,
            "fetch_index_history",
            lambda code: [
                {"dEven": 20260908, "xNivInuClMresIbs": 1.0},
                {"dEven": "bad-date", "xNivInuClMresIbs": 2.0},
                {"dEven": 20260909, "xNivInuClMresIbs": None},
            ],
        )

        bs.sync_benchmark_history()

        db = self._fresh_session(db_session)
        try:
            rows = db.query(BenchmarkHistory).count()
            assert rows == 1
        finally:
            db.close()

    def test_empty_provider_response_is_safe(self, db_session, monkeypatch):
        self._patch_session(monkeypatch, db_session)
        monkeypatch.setattr(
            bs.provider,
            "fetch_index_history",
            lambda code: [],
        )

        bs.sync_benchmark_history()  # must not raise

        db = self._fresh_session(db_session)
        try:
            assert db.query(BenchmarkHistory).count() == 0
        finally:
            db.close()

    def test_stores_under_tehran_total_index_code(self, db_session, monkeypatch):
        self._patch_session(monkeypatch, db_session)
        monkeypatch.setattr(
            bs.provider,
            "fetch_index_history",
            lambda code: _index_items(2),
        )

        bs.sync_benchmark_history()

        db = self._fresh_session(db_session)
        try:
            codes = {
                row.benchmark_code
                for row in db.query(BenchmarkHistory).all()
            }
            assert codes == {TEHRAN_TOTAL_INDEX.code}
        finally:
            db.close()
