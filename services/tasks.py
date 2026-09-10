import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from core.database import SessionLocal
from core.repositories import ETFRepository
from core.models import Fund, ETFMarket
from services.providers import TSETMCProvider
from services.etf_analytics import calculate_premium_discount

logger = logging.getLogger(__name__)


def iran_time():
    return datetime.now(ZoneInfo("Asia/Tehran")).replace(tzinfo=None)


market_provider = TSETMCProvider()

def update_etf_market_data():
    logger.info("Starting live ETF market data collection...")
    db = SessionLocal()
    etf_repo = ETFRepository(db)

    try:
        etf_data = market_provider.fetch_live_etf_prices()
        if not etf_data:
            return

        # فاز ۱ — شبکه: همه درخواست‌های تکمیلی (NAV صدور/ابطال، هویت ابزار)
        # قبل از شروع تراکنش نوشتن انجام می‌شوند. باز نگه داشتن write transaction
        # در طول ده‌ها درخواست شبکه (که هرکدام می‌تواند ثانیه‌ها timeout بخورد)
        # قفل‌های دیتابیس را ده‌ها دقیقه نگه می‌دارد — درس فاز ۷ سند ۶.
        sector_known = {
            ins_code
            for (ins_code,) in (
                db.query(ETFMarket.ins_code)
                .filter(ETFMarket.sector.isnot(None))
                .all()
            )
        }
        db.rollback()  # پایان تراکنش فقط‌خواندنی — از اینجا به بعد شبکه‌ایم، نه دیتابیسی

        prepared = []
        for item in etf_data:
            ins_code = item.get("insCode")
            if not ins_code:
                continue

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

            # NAV را از داده‌ی بازار می‌گیریم؛ اگر موجود نبود از Instrument Info استفاده می‌کنیم
            if not data.get('nav'):
                instrument_info = market_provider.fetch_etf_instrument_info(ins_code)
                if instrument_info and instrument_info.get('nav'):
                    data['nav'] = instrument_info['nav']

            # قیمت‌های redemption/subscription را جداگانه از API اختصاصی می‌گیریم
            if not data.get('nav_red') or not data.get('nav_sub'):
                etf_nav = market_provider.fetch_etf_nav(ins_code)
                if etf_nav:
                    data['nav_red'] = etf_nav.get('pRedTran')
                    data['nav_sub'] = etf_nav.get('pSubTran')

            nav = data.get('nav')
            data['premium_discount'] = calculate_premium_discount(
                market_price=data.get('last_price'),
                nav=nav,
            )

            identity = None
            if ins_code not in sector_known:
                identity = market_provider.fetch_instrument_identity(ins_code)

            prepared.append((ins_code, symbol, name, data, identity))

        # فاز ۲ — ذخیره: تراکنش کوتاه، بدون هیچ درخواست شبکه
        for ins_code, symbol, name, data, identity in prepared:
            etf_repo.upsert_etf_market(ins_code, symbol, name, data)
            etf = etf_repo.get_etf_by_ins_code(ins_code)

            if identity and etf:
                etf.symbol = identity.get("symbol") or identity.get("lVal18AFC")
                etf.sector = identity.get("sector") or identity.get("sectorName")
                etf.subsector = identity.get("subSector") or identity.get("subSectorName")
                etf.market = identity.get("market")
                etf.instrument_status = identity.get("status")

            fund = db.query(Fund).filter(Fund.ins_code == ins_code).first()
            if not fund:
                from services.preprocessing import normalize_fund_name
                norm_symbol = normalize_fund_name(symbol)

                for u_fund in db.query(Fund).filter(Fund.ins_code == None).all():
                    norm_fund_name = normalize_fund_name(u_fund.name)
                    if norm_symbol and norm_symbol in norm_fund_name:
                        u_fund.ins_code = ins_code
                        u_fund.is_etf = True
                        break

            etf_repo.add_etf_history(ins_code, data, observed_at=iran_time())

        db.commit()
        logger.info(f"Successfully updated {len(prepared)} ETF market prices.")
    except Exception as e:
        db.rollback()
        logger.error(f"Error in ETF market update: {e}")
    finally:
        db.close()