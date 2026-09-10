"""قوانین اعتبارسنجی داده (Data Validation Rules).

تسک صریحاً می‌خواهد: «پس از هر بار دریافت اطلاعات، از تکمیل بودن و صحت
اطلاعات اطمینان حاصل شود و در صورت وجود مشکلی از روش‌های پیش‌پردازش برای
رفع آن استفاده شود». این ماژول همان لایه «صحت» است:

- قوانین خالص (pure) هستند: ورودی عدد/لیست، خروجی گزارش تخلف — بدون
  وابستگی به دیتابیس یا شبکه، و در نتیجه کاملاً تست‌پذیر.
- دو مصرف‌کننده دارند:
    ۱. مسیر زنده (fund_sync): اعتبارسنجی سبک inline + قرنطینه رکوردهای بحرانی
    ۲. جاروب دوره‌ای (worker هر ۱۵ دقیقه): تشخیص outlier آماری، شکاف
       زمانی و کهنگی داده روی سری‌های تاریخی
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from statistics import median, stdev
from typing import Sequence

logger = logging.getLogger(__name__)

# آستانه‌ها (به‌صورت ثابت در یک‌جا تا قابل تنظیم و مستند باشند)
CROSS_FIELD_TOLERANCE = 0.10      # اختلاف نسبی مجاز |nav×units − AUM| / AUM
NAV_MOVE_ALERT = 0.25             # حرکت روزانه NAV بیش از ۲۵٪ → هشدار
OUTLIER_Z_THRESHOLD = 4.0         # |z| بازده > ۴ → outlier آماری
OUTLIER_MIN_RETURNS = 5           # حداقل تعداد بازده برای محاسبه z-score
OUTLIER_MIN_ABS_MOVE = 0.05       # کف معناداری: بازده کمتر از ۵٪ هرگز outlier نیست
MAX_GAP_DAYS = 30                 # شکاف بیش از ۳۰ روز بین مشاهدات → هشدار (خوراک منبع change-based است و سکوت چندروزه طبیعی است)
STALENESS_DAYS = 10               # آخرین مشاهده قدیمی‌تر از ۱۰ روز → کهنگی
STALENESS_DAYS_MARKET_MAKING = 90  # صندوق‌های بازارگردانی NAV را به‌ندرت منتشر می‌کنند
FUND_TYPE_MARKET_MAKING = 11

SEVERITY_CRITICAL = "critical"
SEVERITY_WARNING = "warning"
SEVERITY_INFO = "info"

RULE_CROSS_FIELD = "cross_field"
RULE_NAV_MOVE = "nav_move"
RULE_OUTLIER = "outlier"
RULE_GAP = "gap"
RULE_STALENESS = "staleness"


@dataclass
class ValidationIssue:
    """یک تخلف شناسایی‌شده — واحد ثبت در جدول data_quality_issues."""
    fund_reg_no: int
    rule: str
    severity: str
    observed_at: datetime
    detail: str = ""


def cross_field_error(
    nav: float | None,
    units: float | None,
    net_asset: float | None,
    tolerance: float = CROSS_FIELD_TOLERANCE,
) -> float | None:
    """خطای نسبی |nav×units − AUM| / AUM — ناسازگاری بین فیلدهای یک رکورد.

    صفر/ناموجود بودن هر سه مقدار یعنی داده نداریم (نقض نیست، پوشش آن را
    سنجش می‌کند). فقط وقتی هر سه مقدار مثبت باشند قابل ارزیابی است.
    """
    if not nav or not units or not net_asset:
        return None

    implied = nav * units
    error = abs(implied - net_asset) / net_asset

    return error if error > tolerance else None


def nav_move_ratio(
    prev_nav: float | None,
    nav: float | None,
) -> float | None:
    """نسبت تغییر NAV نسبت به مشاهده قبلی."""
    if not prev_nav or not nav:
        return None
    return abs((nav / prev_nav) - 1.0)


def detect_outlier_returns(
    navs: Sequence[float | None],
    z_threshold: float = OUTLIER_Z_THRESHOLD,
    min_returns: int = OUTLIER_MIN_RETURNS,
    min_abs_move: float = OUTLIER_MIN_ABS_MOVE,
) -> list[tuple[int, float]]:
    """بازده‌های خارج از توزیع (z-score مقاوم با MAD) — ایندکس و مقدار z.

    z-score کلاسیک (میانگین/انحراف معیار) در برابر خود outlier آلوده
    می‌شود — به‌ویژه در خوراک change-based که تعداد مشاهدات کم است.
    به همین دلیل از مقیاس مقاوم MAD (انحراف مطلق از میانه) استفاده
    می‌شود، و کف معناداری ۵٪ تضمین می‌کند حرکت‌های کوچک آماری
    «معنادار» ولی عملاً بی‌اهمیت، گزارش نشوند.
    """
    values = [nav for nav in navs if nav is not None]
    if len(values) < 2:
        return []

    returns = [
        (values[i] / values[i - 1]) - 1.0
        for i in range(1, len(values))
        if values[i - 1] > 0
    ]

    if len(returns) < min_returns:
        return []

    center = median(returns)
    mad = median([abs(ret - center) for ret in returns])

    if mad > 0:
        # 0.6745: ضریب سازگاری MAD با انحراف معیار توزیع نرمال
        scale = mad / 0.6745
    else:
        # بیش از نیمی از بازده‌ها یکسان‌اند (خوراک change-based) — MAD صفر
        # می‌شود؛ در این حالت به انحراف معیار کلاسیک برمی‌گردیم که دقیقاً
        # همین جا بیشترین قدرت تشخیص را دارد.
        scale = stdev(returns)
        if scale == 0:
            return []

    outliers = []
    for i, ret in enumerate(returns):
        z = (ret - center) / scale
        if abs(z) > z_threshold and abs(ret) > min_abs_move:
            outliers.append((i + 1, round(z, 2)))

    return outliers


def detect_large_gaps(
    dates: Sequence[datetime | None],
    max_gap_days: int = MAX_GAP_DAYS,
) -> list[tuple[datetime, datetime, int]]:
    """شکاف‌های زمانی بزرگ بین مشاهدات متوالی (تغییر مبنا، قطع منبع و ...)."""
    valid = sorted(d for d in dates if d is not None)
    gaps = []

    for prev, current in zip(valid, valid[1:]):
        gap_days = (current - prev).days
        if gap_days > max_gap_days:
            gaps.append((prev, current, gap_days))

    return gaps


def staleness_days(
    latest_observation: datetime | None,
    now: datetime | None = None,
) -> int | None:
    """فاصله آخرین مشاهده تا اکنون (روز)."""
    if latest_observation is None:
        return None
    now = now or datetime.now()
    return (now - latest_observation).days


def validate_live_record(
    reg_no: int,
    nav: float | None,
    units: float | None,
    net_asset: float | None,
    prev_nav: float | None,
    observed_at: datetime,
) -> list[ValidationIssue]:
    """اعتبارسنجی سبک یک رکورد زنده (بدون نیاز به تاریخچه).

    - ناسازگاری nav×units با AUM → بحرانی (قرنطینه)
    - حرکت غیرعادی NAV نسبت به قبلی → هشدار (ثبت + نگهداری داده)
    """
    issues = []

    error = cross_field_error(nav, units, net_asset)
    if error is not None:
        issues.append(ValidationIssue(
            fund_reg_no=reg_no,
            rule=RULE_CROSS_FIELD,
            severity=SEVERITY_CRITICAL,
            observed_at=observed_at,
            detail=(
                f"nav×units با net_asset ناسازگار است "
                f"(خطای نسبی {error:.1%}، آستانه {CROSS_FIELD_TOLERANCE:.0%})"
            ),
        ))

    move = nav_move_ratio(prev_nav, nav)
    if move is not None and move > NAV_MOVE_ALERT:
        issues.append(ValidationIssue(
            fund_reg_no=reg_no,
            rule=RULE_NAV_MOVE,
            severity=SEVERITY_WARNING,
            observed_at=observed_at,
            detail=f"تغییر NAV به اندازه {move:.1%} در یک مشاهده",
        ))

    return issues


def sweep_fund_history(
    reg_no: int,
    navs: Sequence[float | None],
    dates: Sequence[datetime | None],
    fund_type: int | None = None,
) -> list[ValidationIssue]:
    """جاروب کامل سری زمانی یک صندوق (برای جاب دوره‌ای).

    - outlier آماری بازده‌ها (z-score مقاوم با MAD)
    - شکاف‌های زمانی بزرگ
    - کهنگی آخرین مشاهده (با آستانه متفاوت برای صندوق‌های بازارگردانی
      که NAV را به‌ندرت منتشر می‌کنند)
    """
    if len(navs) != len(dates):
        raise ValueError("navs and dates must have the same length")

    issues = []

    for index, z in detect_outlier_returns(navs):
        issues.append(ValidationIssue(
            fund_reg_no=reg_no,
            rule=RULE_OUTLIER,
            severity=SEVERITY_WARNING,
            observed_at=dates[index] or datetime.min,
            detail=(
                f"بازده خارج از توزیع: z-score = {z} "
                f"(آستانه {OUTLIER_Z_THRESHOLD})"
            ),
        ))

    for start, _, gap_days in detect_large_gaps(dates):
        issues.append(ValidationIssue(
            fund_reg_no=reg_no,
            rule=RULE_GAP,
            severity=SEVERITY_INFO,
            observed_at=start,
            detail=f"شکاف {gap_days} روزه بین مشاهدات متوالی",
        ))

    staleness_threshold = (
        STALENESS_DAYS_MARKET_MAKING
        if fund_type == FUND_TYPE_MARKET_MAKING
        else STALENESS_DAYS
    )

    latest = dates[-1] if dates else None
    days = staleness_days(latest)
    if days is not None and days > staleness_threshold:
        issues.append(ValidationIssue(
            fund_reg_no=reg_no,
            rule=RULE_STALENESS,
            severity=SEVERITY_INFO,
            observed_at=latest,
            detail=f"آخرین مشاهده {days} روز پیش است",
        ))

    return issues
