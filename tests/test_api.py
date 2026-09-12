from datetime import timedelta

from core.models import Fund, FundHistory, ETFMarket, HistoryBackfillState
from core.repositories import iran_time

def test_dashboard_home(client, db_session):
    # فراخوانی API صفحه اصلی
    response = client.get("/")
    
    # بررسی صحت پاسخ و کلماتی که الان واقعاً در صفحه اصلی هستند
    assert response.status_code == 200
    assert "داشبورد مانیتورینگ صندوق‌های سهامی" in response.text
    assert "سهامی (Stock)" in response.text

def test_category_page(client, db_session):
    # 1. اضافه کردن دیتای تستی
    fund = Fund(reg_no=111, name="صندوق تست سهامی", fund_type=6, nav_stat=15000)
    db_session.add(fund)
    db_session.commit()
    
    # 2. فراخوانی API صفحه دسته‌بندی 6 (سهامی)
    response = client.get("/category/6")
    
    # 3. اینجا باید نام صندوق در جدول رندر شده باشد
    assert response.status_code == 200
    assert "صندوق‌های سهامی (Stock)" in response.text
    assert "صندوق تست سهامی" in response.text
    assert "15,000" in response.text # چک کردن فرمت پولی

def test_etf_live_board(client, db_session):
    etf = ETFMarket(ins_code="999", symbol="تست‌یکم", name="صندوق ETF تست", closing_price=10000, price_change=150)
    db_session.add(etf)
    db_session.commit()

    response = client.get("/etf-live")

    assert response.status_code == 200
    assert "تست‌یکم" in response.text
    assert "10,000" in response.text


class TestHistoryBackfillProgress:
    """قانون «کامل» در پیشرفت بک‌فیل: حد نصاب ۹۰ رکورد، یا هر آنچه منبع دارد."""

    def _fund(self, db_session, reg_no):
        fund = Fund(reg_no=reg_no, name=f"Fund {reg_no}", fund_type=6, net_asset=1e9)
        db_session.add(fund)
        db_session.commit()
        return fund

    def _history(self, db_session, reg_no, count):
        for i in range(count):
            db_session.add(
                FundHistory(
                    fund_reg_no=reg_no,
                    observed_at=iran_time() - timedelta(days=i),
                    nav_stat=100.0 + i,
                )
            )
        db_session.commit()

    def test_full_history_is_complete(self, client, db_session):
        self._fund(db_session, 101)
        self._history(db_session, 101, 90)

        data = client.get("/api/dashboard/history-backfill").json()

        assert data["total"] == 1
        assert data["complete"] == 1
        assert data["missing"] == 0
        assert data["source_limited"] == 0

    def test_verified_short_source_counts_as_complete(self, client, db_session):
        self._fund(db_session, 102)
        self._history(db_session, 102, 3)
        db_session.add(
            HistoryBackfillState(
                fund_reg_no=102,
                checked_at=iran_time(),
                source_count=3,
            )
        )
        db_session.commit()

        data = client.get("/api/dashboard/history-backfill").json()

        assert data["complete"] == 1
        assert data["source_limited"] == 1
        assert data["missing"] == 0

    def test_unverified_short_history_counts_as_missing(self, client, db_session):
        self._fund(db_session, 103)
        self._history(db_session, 103, 3)

        data = client.get("/api/dashboard/history-backfill").json()

        assert data["complete"] == 0
        assert data["missing"] == 1

    def test_stale_verification_counts_as_missing(self, client, db_session):
        self._fund(db_session, 104)
        self._history(db_session, 104, 3)
        db_session.add(
            HistoryBackfillState(
                fund_reg_no=104,
                checked_at=iran_time() - timedelta(hours=48),
                source_count=3,
            )
        )
        db_session.commit()

        data = client.get("/api/dashboard/history-backfill").json()

        assert data["missing"] == 1

    def test_source_grew_beyond_stored_counts_as_missing(self, client, db_session):
        self._fund(db_session, 105)
        self._history(db_session, 105, 3)
        db_session.add(
            HistoryBackfillState(
                fund_reg_no=105,
                checked_at=iran_time(),
                source_count=5,
            )
        )
        db_session.commit()

        data = client.get("/api/dashboard/history-backfill").json()

        assert data["missing"] == 1