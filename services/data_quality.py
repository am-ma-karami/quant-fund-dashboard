def calculate_coverage(
    expected: int,
    received: int,
) -> float:
    """محاسبه درصد پوشش دریافت داده نسبت به مقدار مورد انتظار."""
    if expected <= 0:
        return 0.0

    return received / expected
