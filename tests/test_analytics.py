from pytest import approx

from services.analytics import simple_return, normalized_series


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
