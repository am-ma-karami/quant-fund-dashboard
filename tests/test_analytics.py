from pytest import approx

from services.analytics import (
    simple_return,
    normalized_series,
    cumulative_return,
    annualized_return,
    active_return,
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
