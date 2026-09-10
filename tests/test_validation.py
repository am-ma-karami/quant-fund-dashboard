"""Regression tests for the data validation rules (services/validation.py)."""
from datetime import datetime, timedelta

import pytest

from services.validation import (
    cross_field_error,
    nav_move_ratio,
    detect_outlier_returns,
    detect_large_gaps,
    staleness_days,
    validate_live_record,
    sweep_fund_history,
    RULE_CROSS_FIELD,
    RULE_NAV_MOVE,
    RULE_OUTLIER,
    RULE_GAP,
    RULE_STALENESS,
    SEVERITY_CRITICAL,
    SEVERITY_WARNING,
    SEVERITY_INFO,
)


class TestCrossFieldError:
    def test_consistent_record_passes(self):
        # nav × units = net_asset دقیقاً
        assert cross_field_error(1000.0, 5000.0, 5_000_000.0) is None

    def test_small_rounding_error_passes(self):
        # خطای ۰٫۵٪ زیر آستانه ۱۰٪
        assert cross_field_error(1005.0, 5000.0, 5_000_000.0) is None

    def test_broken_record_flagged(self):
        error = cross_field_error(2000.0, 5000.0, 5_000_000.0)
        assert error is not None
        assert error == pytest.approx(1.0)  # دو برابر شدن

    def test_missing_values_are_skipped(self):
        assert cross_field_error(0.0, 5000.0, 5_000_000.0) is None
        assert cross_field_error(1000.0, 0.0, 5_000_000.0) is None
        assert cross_field_error(1000.0, 5000.0, 0.0) is None
        assert cross_field_error(None, 5000.0, 5_000_000.0) is None


class TestNavMoveRatio:
    def test_normal_move(self):
        assert nav_move_ratio(100.0, 105.0) == pytest.approx(0.05)

    def test_missing_values(self):
        assert nav_move_ratio(0.0, 105.0) is None
        assert nav_move_ratio(100.0, 0.0) is None
        assert nav_move_ratio(None, 105.0) is None


class TestDetectOutlierReturns:
    def test_clean_series_no_outliers(self):
        navs = [100.0 * (1.01 ** i) for i in range(30)]  # رشد ثابت ۱٪
        assert detect_outlier_returns(navs) == []

    def test_spike_flagged(self):
        navs = [100.0 * (1.01 ** i) for i in range(30)]
        navs[15] *= 2.0  # جهش ۱۰۰٪ در یک روز
        outliers = detect_outlier_returns(navs)
        assert outliers, "spike must be detected"
        assert any(index == 15 for index, _ in outliers)

    def test_too_few_returns(self):
        assert detect_outlier_returns([100.0, 105.0]) == []

    def test_none_values_handled(self):
        navs = [100.0 * (1.01 ** i) for i in range(20)]
        navs.insert(5, None)
        assert detect_outlier_returns(navs) == []

    def test_small_moves_never_flagged(self):
        # نمونه کوچک با حرکت‌های ۲٪: از نظر آماری ممکن است z بالا بگیرند
        # اما کف معناداری ۵٪ مانع گزارش آن‌ها می‌شود (کاهش نویز)
        navs = [100.0, 102.0, 104.0, 101.0, 103.0, 105.0]
        assert detect_outlier_returns(navs) == []


class TestDetectLargeGaps:
    def _date(self, days_ago):
        return datetime(2026, 9, 10) - timedelta(days=days_ago)

    def test_no_large_gaps(self):
        dates = sorted(self._date(i) for i in range(0, 20, 2))
        assert detect_large_gaps(dates) == []

    def test_large_gap_detected(self):
        dates = sorted([
            self._date(0),
            self._date(1),
            self._date(60),  # شکاف ۵۹ روزه
        ])
        gaps = detect_large_gaps(dates)
        assert len(gaps) == 1
        assert gaps[0][2] == 59

    def test_none_dates_skipped(self):
        dates = [self._date(50), None, self._date(0)]
        assert len(detect_large_gaps(dates)) == 1


class TestStaleness:
    def test_fresh(self):
        assert staleness_days(datetime.now() - timedelta(days=2), datetime.now()) == 2

    def test_none(self):
        assert staleness_days(None) is None


class TestValidateLiveRecord:
    def test_clean_record_no_issues(self):
        issues = validate_live_record(
            reg_no=1,
            nav=1000.0,
            units=5000.0,
            net_asset=5_000_000.0,
            prev_nav=990.0,
            observed_at=datetime(2026, 9, 10),
        )
        assert issues == []

    def test_cross_field_broken_is_critical(self):
        issues = validate_live_record(
            reg_no=1,
            nav=2000.0,
            units=5000.0,
            net_asset=5_000_000.0,
            prev_nav=1000.0,
            observed_at=datetime(2026, 9, 10),
        )
        cross = [i for i in issues if i.rule == RULE_CROSS_FIELD]
        assert len(cross) == 1
        assert cross[0].severity == SEVERITY_CRITICAL

    def test_large_nav_move_is_warning(self):
        issues = validate_live_record(
            reg_no=1,
            nav=1500.0,  # +۵۰٪ نسبت به قبلی
            units=5000.0,
            net_asset=7_500_000.0,
            prev_nav=1000.0,
            observed_at=datetime(2026, 9, 10),
        )
        moves = [i for i in issues if i.rule == RULE_NAV_MOVE]
        assert len(moves) == 1
        assert moves[0].severity == SEVERITY_WARNING


class TestSweepFundHistory:
    def _recent_dates(self, count):
        return [
            datetime(2026, 9, 10) - timedelta(days=i)
            for i in range(count)
        ][::-1]

    def test_clean_history_no_issues(self):
        navs = [100.0 * (1.01 ** i) for i in range(40)]
        dates = self._recent_dates(40)
        assert sweep_fund_history(1, navs, dates) == []

    def test_stale_history_flagged(self):
        navs = [100.0, 101.0]
        dates = [datetime(2026, 6, 1), datetime(2026, 6, 2)]
        issues = sweep_fund_history(1, navs, dates)
        assert any(i.rule == RULE_STALENESS for i in issues)
        assert any(i.severity == SEVERITY_INFO for i in issues)

    def test_market_making_fund_staleness_threshold_is_looser(self):
        # صندوق بازارگردانی (نوع ۱۱) که ۶۰ روز است داده‌ای منتشر نکرده —
        # این رفتار طبیعی است و نباید کهنه محسوب شود (آستانه ۹۰ روز)
        old = datetime.now() - timedelta(days=60)
        navs = [100.0, 101.0]
        dates = [old, old + timedelta(days=1)]
        issues = sweep_fund_history(1, navs, dates, fund_type=11)
        assert not any(i.rule == RULE_STALENESS for i in issues)

        # اما صندوق عادی با همان تاریخ‌ها کهنه است (آستانه ۱۰ روز)
        issues = sweep_fund_history(1, navs, dates, fund_type=6)
        assert any(i.rule == RULE_STALENESS for i in issues)

    def test_gap_flagged(self):
        navs = [100.0, 101.0, 102.0]
        dates = [
            datetime(2026, 7, 1),
            datetime(2026, 7, 2),
            datetime(2026, 9, 1),  # شکاف ~۶۰ روزه
        ]
        issues = sweep_fund_history(1, navs, dates)
        assert any(i.rule == RULE_GAP for i in issues)

    def test_outlier_flagged(self):
        navs = [100.0 * (1.01 ** i) for i in range(40)]
        navs[20] *= 3.0
        dates = self._recent_dates(40)
        issues = sweep_fund_history(1, navs, dates)
        assert any(i.rule == RULE_OUTLIER for i in issues)
        assert any(i.severity == SEVERITY_WARNING for i in issues)

    def test_length_mismatch_raises(self):
        with pytest.raises(ValueError):
            sweep_fund_history(1, [1.0, 2.0], [datetime(2026, 9, 1)])
