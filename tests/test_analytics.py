from pytest import approx

from services.analytics import (
    simple_return,
    normalized_series,
    cumulative_return,
    annualized_return,
    active_return,
    drawdown_series,
    fund_flows,
    index_to_100,
    cumulative_sum,
)


def test_simple_return():
    assert simple_return(110, 100) == approx(0.1)
    assert simple_return(90, 100) == approx(-0.1)


def test_simple_return_invalid():
    assert simple_return(None, 100) is None
    assert simple_return(100, 0) is None


def test_normalized_series():
    assert normalized_series([100, 110, 90]) == approx([100.0, 110.0, 90.0])


def test_normalized_series_empty():
    assert normalized_series([]) == []


def test_cumulative_return():
    assert cumulative_return([100, 110]) == approx(0.10)


def test_cumulative_return_insufficient():
    assert cumulative_return([100]) is None


def test_annualized_return():
    result = annualized_return([100, 110, 121], periods_per_year=12)
    assert result is not None
    assert result > 1.0


def test_active_return():
    assert active_return(0.20, 0.10) == approx(0.10)
    assert active_return(None, 0.10) is None
    assert active_return(0.20, None) is None


def test_drawdown_series():
    # 100 → 120 (سقف) → 90 (۲۵٪ زیر سقف) → 60 (۵۰٪ زیر سقف) → 120 (روی سقف)
    result = drawdown_series([100, 120, 90, 60, 120])
    assert result == approx([0.0, 0.0, -0.25, -0.5, 0.0])


def test_drawdown_series_with_none():
    result = drawdown_series([100, None, 50])
    assert result[0] == approx(0.0)
    assert result[1] is None
    assert result[2] == approx(-0.5)


def test_drawdown_series_empty():
    assert drawdown_series([]) == []


def test_fund_flows_no_flow_when_aum_tracks_nav():
    # AUM دقیقاً با بازده NAV رشد می‌کند → جریان صفر
    navs = [100, 110, 121]
    aums = [1000, 1100, 1210]
    result = fund_flows(navs, aums)
    assert result[0] is None
    assert result[1:] == approx([0.0, 0.0])


def test_fund_flows_inflow_detected():
    # NAV ثابت، AUM رشد کرد → ورود پول
    navs = [100, 100, 100]
    aums = [1000, 2000, 1500]
    result = fund_flows(navs, aums)
    assert result[1] == approx(1000.0)
    assert result[2] == approx(-500.0)


def test_fund_flows_return_effect_excluded():
    # NAV از ۱۰۰ به ۱۲۰ (۲۰٪ رشد)، AUM از ۱۰۰۰ به ۱۵۰۰
    # رشد توضیح‌داده‌شده: ۱۲۰۰ → جریان = ۳۰۰
    result = fund_flows([100, 120], [1000, 1500])
    assert result[1] == approx(300.0)


def test_index_to_100():
    assert index_to_100([200, 220, 180]) == approx([100.0, 110.0, 90.0])


def test_index_to_100_with_none():
    result = index_to_100([200, None, 180])
    assert result[0] == approx(100.0)
    assert result[1] is None
    assert result[2] == approx(90.0)


def test_index_to_100_empty():
    assert index_to_100([]) == []
    assert index_to_100([None]) == [None]


def test_cumulative_sum():
    assert cumulative_sum([10, -5, 20]) == approx([10.0, 5.0, 25.0])
    assert cumulative_sum([10, None, 20]) == [10.0, None, 30.0]
