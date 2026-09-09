from math import sqrt
from statistics import mean, stdev


def returns_from_prices(
    prices: list[float],
) -> list[float]:
    """محاسبه بازده ساده بین نقاط متوالی قیمت."""
    if len(prices) < 2:
        return []

    returns = []

    for previous, current in zip(prices, prices[1:]):
        if previous == 0:
            continue

        returns.append(
            (current / previous) - 1.0
        )

    return returns


def annualized_volatility(
    returns: list[float],
    periods_per_year: int = 252,
) -> float | None:
    """نوسان‌پذیری سالانه‌شده."""
    if len(returns) < 2:
        return None

    return stdev(returns) * sqrt(periods_per_year)


def sharpe_ratio(
    returns: list[float],
    risk_free_rate: float = 0.0,
    periods_per_year: int = 252,
) -> float | None:
    """نسبت شارپ سالانه‌شده."""
    if len(returns) < 2:
        return None

    avg_return = mean(returns)
    volatility = stdev(returns)

    if volatility == 0:
        return None

    periodic_rf = risk_free_rate / periods_per_year

    return (
        (avg_return - periodic_rf)
        / volatility
        * sqrt(periods_per_year)
    )


def maximum_drawdown(
    prices: list[float],
) -> float | None:
    """حداکثر افت از سقف تاریخی."""
    if not prices:
        return None

    peak = prices[0]
    max_drawdown = 0.0

    for price in prices:
        if price > peak:
            peak = price

        if peak == 0:
            continue

        drawdown = (price / peak) - 1.0

        max_drawdown = min(
            max_drawdown,
            drawdown,
        )

    return max_drawdown
