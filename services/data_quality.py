def calculate_coverage(
    expected: int,
    received: int,
) -> float:
    """محاسبه درصد پوشش دریافت داده نسبت به مقدار مورد انتظار."""
    if expected <= 0:
        return 0.0

    return received / expected


def calculate_quality_score(
    expected: int,
    received: int,
    valid: int,
    failed: int,
) -> float:
    if expected <= 0:
        return 0.0

    completeness = received / expected
    validity = valid / received if received else 0.0
    failure_rate = failed / expected

    score = (
        completeness * 50
        + validity * 40
        + max(0.0, 1.0 - failure_rate) * 10
    )

    return round(score, 2)
