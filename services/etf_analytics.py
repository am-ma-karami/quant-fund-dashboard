from statistics import mean, stdev


def calculate_premium_discount(
    market_price: float | None,
    nav: float | None,
) -> float | None:
    """محاسبه درصد اختلاف قیمت بازار از NAV ذاتی."""
    if market_price is None or nav is None:
        return None

    if nav <= 0:
        return None

    return ((market_price / nav) - 1.0) * 100.0


def calculate_premium_stats(
    premium_values: list[float],
) -> dict:
    values = [
        value
        for value in premium_values
        if value is not None
    ]

    if len(values) < 2:
        return {
            "mean": None,
            "std": None,
            "zscore": None,
        }

    avg = mean(values)
    sigma = stdev(values)

    return {
        "mean": avg,
        "std": sigma,
    }


def calculate_premium_zscore(
    current: float | None,
    historical: list[float],
) -> float | None:
    values = [
        value
        for value in historical
        if value is not None
    ]

    if current is None or len(values) < 2:
        return None

    avg = mean(values)
    sigma = stdev(values)

    if sigma == 0:
        return None

    return (current - avg) / sigma
