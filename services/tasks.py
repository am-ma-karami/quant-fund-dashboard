import asyncio
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx

from core.database import SessionLocal
from core.repositories import ETFRepository
from core.models import Fund, ETFMarket
from services.providers import TSETMCProvider
from services.etf_analytics import calculate_premium_discount
from services.preprocessing import normalize_fund_name

logger = logging.getLogger(__name__)


def iran_time():
    return datetime.now(ZoneInfo("Asia/Tehran")).replace(tzinfo=None)


market_provider = TSETMCProvider()

# سقف همزمانی درخواست‌های تکمیلی فاز شبکه: fan-out را محدود می‌کند تا
# منبع داده (TSETMC) زیر بار ده‌ها درخواست همزمان له نشود. با ~۵۰ ردیف
# تابلوی ETF و timeout پنج ثانیه‌ای، بدترین حالت چرخه حدود ۳ موج × ۵
# ثانیه ≈ ۱۵ ثانیه است — در برابر ~۴۰ دقیقه نسخه ترتیبی (مشاهده واقعی).
MAX_ENRICHMENT_CONCURRENCY = 20

# سقف فاصله نسبی مجاز قیمت بازار از NAV برای اینکه یک NAV مبنای
# پریمیوم شود. پریمیوم/تخفیف واقعی ETF در عمل چند درصد حول صفر
# نوسان می‌کند؛ فاصله‌های صدها و هزاران درصدی (که در داده واقعی
# با نگاشت‌های نادرست دیده شد) امضای NAV غلط است، نه بازار واقعی.
NAV_PLAUSIBILITY_BOUND = 0.30


def _nav_distance(price, nav) -> float | None:
    """فاصله نسبی قیمت بازار از NAV — با ورودی نامعتبر، None.

    None به معنی «شواهدی نداریم» است و با «ناسازگار» فرق دارد:
    تصمیم‌ها فقط روی شواهد بنا می‌شوند.
    """
    try:
        price = float(price)
        nav = float(nav)
    except (TypeError, ValueError):
        return None
    if price is None or nav is None or price <= 0 or nav <= 0:
        return None
    return abs(price / nav - 1.0)


def _nav_plausible(price, nav, bound=NAV_PLAUSIBILITY_BOUND) -> bool:
    """آیا NAV با قیمت بازار هم‌مقیاس و سازگار است؟"""
    distance = _nav_distance(price, nav)
    return distance is not None and distance <= bound


def _mapped_nav_contradicts_price(nav_stat, last_price) -> bool:
    """شواهد علیه نگاشت موجود: NAV مثبت ولی به‌وضوح ناسازگار با قیمت.

    شرط مثبت‌بودن قیمت عمدی است: بدون معامله امروز شواهدی وجود
    ندارد و نگاشت دست نمی‌خورد.
    """
    return (
        nav_stat is not None
        and nav_stat > 0
        and last_price is not None
        and last_price > 0
        and not _nav_plausible(last_price, nav_stat)
    )


def _match_fund(db, ins_code, symbol, last_price):
    """نگاشت ETF به صندوق: تطبیق نام + تأیید NAV.

    تطبیق نامی خالص قبلاً false positive می‌ساخت: نرمال‌سازی تهاجمی
    حروف مفرد («د»، «ب»، «س»، «یکم») را از نام‌ها حذف می‌کرد و
    زیررشته‌های کوتاه داخل نام‌های بلندتر می‌نشستند (مثلاً «اون» از
    «آوند» داخل «تعاون»). حالا نام فقط نامزدها را فیلتر می‌کند و
    تصمیم نهایی با NAV است: صندوق واقعی NAVای نزدیک به قیمت بازار
    ETF دارد. نبود هیچ نامزد تأییدشده یعنی نگاشت نمی‌شود — نگاشت
    اشتباه از نبود نگاشت بدتر است.
    """
    norm_symbol = normalize_fund_name(symbol)
    if not norm_symbol:
        return None

    candidates = []
    for u_fund in db.query(Fund).filter(Fund.ins_code == None).all():
        # شرط in-memory هم لازم است: با autoflush=False، نگاشت‌هایی که
        # همین چرخه بسته شده‌اند هنوز فلاش نشده‌اند و شرط SQL آن‌ها را
        # نمی‌بیند — بدون این شرط دو ETF می‌توانند یک صندوق را بربایند.
        if u_fund.ins_code is not None:
            continue
        norm_name = normalize_fund_name(u_fund.name)
        if not norm_name or norm_symbol not in norm_name:
            continue
        distance = _nav_distance(last_price, u_fund.nav_stat)
        if distance is not None and distance <= NAV_PLAUSIBILITY_BOUND:
            candidates.append((distance, u_fund))

    if not candidates:
        return None

    winner = min(candidates, key=lambda pair: pair[0])[1]
    winner.ins_code = ins_code
    winner.is_etf = True
    return winner


def _new_async_client() -> httpx.AsyncClient:
    """ساخت کلاینت async برای فاز شبکه چرخه سینک ETF.

    یک کلاینت در کل چرخه ساخته می‌شود — نه به ازای هر درخواست — تا
    استخر اتصال هزینه برقراری اتصال را برای ده‌ها درخواست تکمیلی
    فقط یک‌بار پرداخت کند. مهندسی: timeout معادل نسخه همگام قبلی
    (۵ ثانیه) است و base_url عمداً داده نمی‌شود تا httpx پیشوند
    ``/api`` را هنگام merge مسیرها از بین نبرد.
    """
    return httpx.AsyncClient(
        headers=market_provider.headers,
        timeout=httpx.Timeout(5.0),
    )


async def _enrich_entry(
    item: dict,
    sector_known: set,
    client: httpx.AsyncClient,
    sem: asyncio.Semaphore,
) -> tuple | None:
    """غنی‌سازی یک ردیف تابلوی ETF — فاز ۱ (شبکه).

    درخواست‌های تکمیلیِ مشروط این ردیف (NAV، قیمت صدور/ابطال، هویت
    ابزار) همزمان اجرا می‌شوند و شکست هرکدام محلی می‌ماند: متدهای
    provider خطاهای HTTP را خودشان می‌بلعند (None/``{}``) و استثنای
    پیش‌بینی‌نشده هم با ``return_exceptions`` به مقدار تبدیل و اینجا
    فیلتر می‌شود — شکست یک endpoint هرگز کل ردیف را نمی‌کشد.
    """
    ins_code = item.get("insCode")
    if not ins_code:
        return None

    instrument = item.get("instrument", {})
    symbol = instrument.get("lVal18AFC", "نامشخص")
    name = instrument.get("lVal30", "نامشخص")

    data = {
        'last_price': item.get("pDrCotVal"),
        'closing_price': item.get("pClosing"),
        'price_change': item.get("priceChange"),
        'total_trades': item.get("zTotTran"),
        'total_volume': item.get("qTotTran5J"),
        'total_value': item.get("qTotCap"),
        'price_min': item.get("priceMin"),
        'price_max': item.get("priceMax"),
        'price_first': item.get("priceFirst"),
        'price_yesterday': item.get("priceYesterday"),
        'nav': item.get("nav"),
        'nav_red': item.get("pRedTran"),
        'nav_sub': item.get("pSubTran"),
    }

    # شغل‌های شرطی این ردیف — فقط آن‌هایی که پاسخ اصلی تابلوی بازار
    # جوابشان را ندارد، تا درخواست بیهوده به منبع داده نزنیم
    jobs = {}
    if not data.get('nav'):
        jobs["info"] = market_provider.fetch_etf_instrument_info(client, ins_code)
    if not data.get('nav_red') or not data.get('nav_sub'):
        jobs["prices"] = market_provider.fetch_etf_nav(client, ins_code)
    if ins_code not in sector_known:
        jobs["identity"] = market_provider.fetch_instrument_identity(client, ins_code)

    async with sem:
        names = list(jobs)
        results = await asyncio.gather(
            *(jobs[name] for name in names),
            return_exceptions=True,
        )
    by_name = dict(zip(names, results))

    # NAV را از داده‌ی بازار می‌گیریم؛ اگر موجود نبود از Instrument Info استفاده می‌کنیم
    info = by_name.get("info")
    if isinstance(info, dict) and info.get('nav'):
        data['nav'] = info['nav']

    # قیمت‌های redemption/subscription را جداگانه از API اختصاصی می‌گیریم
    prices = by_name.get("prices")
    if isinstance(prices, dict) and prices:
        data['nav_red'] = prices.get('pRedTran')
        data['nav_sub'] = prices.get('pSubTran')

    identity = by_name.get("identity")
    if not isinstance(identity, dict):
        identity = None

    # پریمیوم اینجا حساب نمی‌شود: NAV نهایی فقط در فاز ۲ (بعد از نگاشت
    # ETF→صندوق) معلوم می‌شود و همان‌جا یک‌بار و با مبنای درست محاسبه می‌شود.
    return (ins_code, symbol, name, data, identity)


async def update_etf_market_data():
    logger.info("Starting live ETF market data collection...")
    db = SessionLocal()
    etf_repo = ETFRepository(db)

    try:
        etf_data = market_provider.fetch_live_etf_prices()
        if not etf_data:
            return

        # فاز ۱ — شبکه: همه درخواست‌های تکمیلی (NAV صدور/ابطال، هویت ابزار)
        # قبل از شروع تراکنش نوشتن و به‌صورت همزمان (fan-out) انجام می‌شوند.
        # باز نگه داشتن write transaction در طول درخواست‌های شبکه — چه ترتیبی
        # و چه همزمان — قفل‌های دیتابیس را ده‌ها دقیقه نگه می‌دارد (در اجرای
        # واقعی نسخه ترتیبی حدود ۴۰ دقیقه تراکنش باز نگه داشته بود).
        sector_known = {
            ins_code
            for (ins_code,) in (
                db.query(ETFMarket.ins_code)
                .filter(ETFMarket.sector.isnot(None))
                .all()
            )
        }
        db.rollback()  # پایان تراکنش فقط‌خواندنی — از اینجا به بعد شبکه‌ایم، نه دیتابیسی

        async with _new_async_client() as client:
            sem = asyncio.Semaphore(MAX_ENRICHMENT_CONCURRENCY)
            results = await asyncio.gather(
                *(_enrich_entry(item, sector_known, client, sem)
                  for item in etf_data),
                return_exceptions=True,
            )

        prepared = []
        for result in results:
            if result is None:
                continue
            if isinstance(result, Exception):
                # ایزوله‌سازی شکست در سطح ردیف: ردیف خراب ثبت نمی‌شود،
                # بقیه چرخه سالم می‌ماند — و خطا بی‌صدا هم نمی‌ماند
                logger.error(
                    "ETF enrichment failed for one entry; continuing with the rest: %s",
                    result,
                )
                continue
            prepared.append(result)

        # فاز ۲ — ذخیره: تراکنش کوتاه، بدون هیچ درخواست شبکه
        for ins_code, symbol, name, data, identity in prepared:
            last_price = data.get('last_price')
            fund = db.query(Fund).filter(Fund.ins_code == ins_code).first()

            # خودترمیمی نگاشت‌های قدیمی: نگاشت‌هایی که نسخه‌های قبلی فقط
            # با نام بسته بودند و NAV صندوقشان به قیمت بازار ETF نزدیک
            # نیست، باز می‌شوند تا دوباره با محک NAV تطبیق بخورند —
            # یا اگر نامزد تأییدشده‌ای نیست، بی‌نگاشت بمانند.
            if fund and _mapped_nav_contradicts_price(fund.nav_stat, last_price):
                fund.ins_code = None
                fund.is_etf = False
                fund = None

            if not fund:
                fund = _match_fund(db, ins_code, symbol, last_price)

            # مبنای NAV پریمیوم، با محک سازگاری در برابر قیمت بازار.
            # ترتیب منابع: NAV موجود → NAV صندوق متناظر (نگاشت) → قیمت
            # صدور زنده → قیمت ابطال. هر مبنایی که به قیمت نزدیک نیست
            # رد می‌شود — یک NAV غلط پریمیومی صدها درصدی می‌سازد که از
            # نبود پریمیوم بدتر است. بدون مبنای سازگار، پریمیوم NULL
            # می‌ماند (داده‌ای که نداریم، صادقانه نداریم).
            nav = data.get('nav')
            if not _nav_plausible(last_price, nav):
                nav = None
            if nav is None and fund and _nav_plausible(last_price, fund.nav_stat):
                nav = fund.nav_stat
            if nav is None and _nav_plausible(last_price, data.get('nav_sub')):
                nav = data['nav_sub']
            if nav is None and _nav_plausible(last_price, data.get('nav_red')):
                nav = data['nav_red']

            data['nav'] = nav
            data['premium_discount'] = calculate_premium_discount(
                market_price=last_price,
                nav=nav,
            )

            etf_repo.upsert_etf_market(ins_code, symbol, name, data)
            etf = etf_repo.get_etf_by_ins_code(ins_code)

            if identity and etf:
                # هویت ابزار در provider به قرارداد مسطح رشتهای نرمال
                # شده است؛ «or etf.x» یعنی مقدار نامعتبر، مقدار موجود
                # روی تابلوی بازار را نمیپوشاند
                etf.symbol = identity.get("symbol") or etf.symbol
                etf.sector = identity.get("sector") or etf.sector
                etf.subsector = identity.get("subsector") or etf.subsector
                etf.market = identity.get("market") or etf.market

            etf_repo.add_etf_history(ins_code, data, observed_at=iran_time())

        db.commit()
        logger.info(f"Successfully updated {len(prepared)} ETF market prices.")
    except Exception as e:
        db.rollback()
        logger.error(f"Error in ETF market update: {e}")
    finally:
        db.close()


def update_etf_market_data_job():
    """ورودی زمان‌بند برای چرخه async سینک ETF.

    `BlockingScheduler` وظایف را در ThreadPoolExecutor اجرا می‌کند و
    coroutine را مستقیماً نمی‌پذیرد؛ این پوشش برای هر چرخه یک event
    loop مستقل می‌سازد و چرخه async را در آن اجرا می‌کند.
    """
    asyncio.run(update_etf_market_data())
