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
