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
