from math import sqrt
from statistics import mean, stdev
from typing import Sequence


def simple_return(
    current: float | None,
    previous: float | None,
) -> float | None:
    """محاسبه بازده ساده بین دو مقدار."""
    if current is None or previous is None:
        return None

    if previous == 0:
        return None

    return (current / previous) - 1.0


def normalized_series(values: Sequence[float]) -> list[float]:
    """نرمال‌سازی سری زمانی نسبت به مقدار اولیه (Index = 100)."""
    if not values:
        return []

    first = values[0]

    if first == 0:
        return []

    return [
        (value / first) * 100.0
        for value in values
    ]


def cumulative_return(prices: Sequence[float]) -> float | None:
    if len(prices) < 2:
        return None

    first = prices[0]
    last = prices[-1]

    if first <= 0:
        return None

    return (last / first) - 1.0


def annualized_return(
    prices: Sequence[float],
    periods_per_year: int = 252,
) -> float | None:
    if len(prices) < 2:
        return None

    first = prices[0]
    last = prices[-1]

    if first <= 0:
        return None

    periods = len(prices) - 1

    return (last / first) ** (
        periods_per_year / periods
    ) - 1.0


def active_return(
    fund_return: float | None,
    benchmark_return: float | None,
) -> float | None:
    if fund_return is None or benchmark_return is None:
        return None

    return fund_return - benchmark_return
