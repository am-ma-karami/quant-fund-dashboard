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


def drawdown_series(
    prices: Sequence[float | None],
) -> list[float | None]:
    """سری زمانی افت از سقف (Underwater) برای هر مشاهده.

    خروجی نسبت منفی (یا صفر) است: ۰ یعنی روی سقف، ‎-0.2 یعنی ۲۰٪ زیر سقف.
    """
    series = []
    peak = None

    for price in prices:
        if price is None:
            series.append(None)
            continue

        if peak is None or price > peak:
            peak = price

        if peak == 0:
            series.append(None)
            continue

        series.append((price / peak) - 1.0)

    return series


def fund_flows(
    navs: Sequence[float | None],
    aums: Sequence[float | None],
) -> list[float | None]:
    """جریان خالص پول در هر دوره.

    جریان = ΔAUM − اثر بازده NAV روی AUM
    یعنی رشدی از AUM که با بازده NAV توضیح داده نشود، ورود/خروج پول است.
    """
    flows = []
    prev_nav = None
    prev_aum = None

    for nav, aum in zip(navs, aums):
        if nav is None or aum is None:
            flows.append(None)
            prev_nav, prev_aum = nav, aum
            continue

        if prev_nav is not None and prev_aum is not None and prev_nav > 0:
            period_return = (nav / prev_nav) - 1.0
            flows.append(aum - prev_aum * (1 + period_return))
        else:
            flows.append(None)

        prev_nav, prev_aum = nav, aum

    return flows


def index_to_100(
    values: Sequence[float | None],
) -> list[float | None]:
    """نرمال‌سازی سری نسبت به اولین مقدار معتبر (پایه = ۱۰۰)."""
    base = next((value for value in values if value), None)

    if base is None:
        return [None] * len(values)

    return [
        (value / base) * 100.0 if value else None
        for value in values
    ]


def cumulative_sum(
    values: Sequence[float | None],
) -> list[float | None]:
    """مجموع تجمعی با حفظ Noneها (بدون از دست دادن موقعیت)."""
    result = []
    total = 0.0

    for value in values:
        if value is None:
            result.append(None)
            continue
        total += value
        result.append(total)

    return result
