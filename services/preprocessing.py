import logging

logger = logging.getLogger(__name__)


def validate_percentage(
    value,
    field_name: str,
):
    """اعتبارسنجی درصد: مقدار باید عدد و بین ۰ تا ۱۰۰ باشد."""
    if value is None:
        return None

    try:
        value = float(value)
    except (TypeError, ValueError):
        raise ValueError(
            f"{field_name} is not numeric"
        )

    if not 0 <= value <= 100:
        raise ValueError(
            f"{field_name} outside valid range: {value}"
        )

    return value


def clean_fund_data(raw_data: dict) -> dict:
    """
    پیش‌پردازش و پاک‌سازی دیتای خام دریافتی از API بورس
    حفظ مقادیر Null و اعتبارسنجی محدوده‌ی درصدها
    """
    cleaned = {}

    # 1. Validation (اعتبارسنجی): بررسی شماره ثبت
    try:
        cleaned['reg_no'] = int(raw_data.get("regNo", 0))
    except (TypeError, ValueError):
        cleaned['reg_no'] = 0

    # 2. Handling Nulls (حفظ مقادیر خالی به‌جای تبدیل به صفر)
    cleaned['nav_stat'] = raw_data.get("navStat")
    cleaned['nav_sub'] = raw_data.get("navSub")
    cleaned['nav_red'] = raw_data.get("navRed")
    cleaned['net_asset'] = raw_data.get("netAsset")
    cleaned['units'] = raw_data.get("units")

    # 3. Text Normalization (حذف فاصله‌های اضافی و هندل کردن رشته‌های خالی)
    cleaned['name'] = str(raw_data.get("mfName") or "نامشخص").strip()
    cleaned['manager'] = str(raw_data.get("manager") or "نامشخص").strip()

    # 4. Outlier Handling / Constraints
    # درصد دارایی‌ها باید بین صفر و ۱۰۰ باشد
    cleaned['portfolio_stock'] = validate_percentage(
        raw_data.get("portfolioStock"),
        "portfolio_stock",
    )
    cleaned['portfolio_bond'] = validate_percentage(
        raw_data.get("portfolioBond"),
        "portfolio_bond",
    )
    cleaned['portfolio_deposit'] = validate_percentage(
        raw_data.get("portfolioDeposit"),
        "portfolio_deposit",
    )

    # 5. Financial Returns (بازدهی‌ها می‌توانند منفی باشند)
    cleaned['day1_return'] = raw_data.get("day1Return")
    cleaned['day7_return'] = raw_data.get("day7Return")
    cleaned['day30_return'] = raw_data.get("day30Return")
    cleaned['day90_return'] = raw_data.get("day90Return")
    cleaned['day180_return'] = raw_data.get("day180Return")
    cleaned['day365_return'] = raw_data.get("day365Return")

    return cleaned
