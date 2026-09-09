import logging
from datetime import datetime
from zoneinfo import ZoneInfo
from dateutil import parser

from core.database import SessionLocal
from core.repositories import FundRepository, ETFRepository
from services.providers import TSETMCProvider
from services.preprocessing import clean_fund_data
from services.etf_analytics import calculate_premium_discount

logger = logging.getLogger(__name__)

FUND_TYPES = [4, 5, 6, 7, 11, 12, 13, 14, 16, 17]


def iran_time():
    return datetime.now(ZoneInfo("Asia/Tehran")).replace(tzinfo=None)


market_provider = TSETMCProvider()

def update_funds_data():
    logger.info("Starting data collection task for ALL categories...")
    db = SessionLocal()
    fund_repo = FundRepository(db)
    
    try:
        total_updated = 0
        for f_type in FUND_TYPES:
            funds_data = market_provider.fetch_funds_by_type(f_type)
            if not funds_data:
                continue
                
            for item in funds_data:
                clean_item = clean_fund_data(item)
                reg_no = clean_item['reg_no']
                if reg_no == 0:
                    continue
                
                # استفاده از ریپازیتوری برای ذخیره در دیتابیس
                fund_repo.upsert_fund(reg_no, clean_item['name'], f_type, clean_item)
                record_date_str = item.get("recordDate")

                if record_date_str:
                    observed_at = parser.parse(record_date_str)

                    fund_repo.upsert_fund_history(
                        reg_no=reg_no,
                        nav_stat=clean_item["nav_stat"],
                        nav_sub=clean_item["nav_sub"],
                        nav_red=clean_item["nav_red"],
                        net_asset=clean_item["net_asset"],
                        units=clean_item["units"],
                        observed_at=observed_at,
                    )

                total_updated += 1
                
        db.commit()
        logger.info(f"Successfully updated {total_updated} funds.")
    except Exception as e:
        db.rollback()
        logger.error(f"Database error during update: {e}")
    finally:
        db.close()

def update_etf_market_data():
    logger.info("Starting live ETF market data collection...")
    db = SessionLocal()
    etf_repo = ETFRepository(db)
    
    try:
        etf_data = market_provider.fetch_live_etf_prices()
        if not etf_data:
            return

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
            
            etf_repo.upsert_etf_market(ins_code, symbol, name, data)
            etf = etf_repo.get_etf_by_ins_code(ins_code)

            if etf and (not etf.symbol or not etf.sector):
                identity = market_provider.fetch_instrument_identity(ins_code)

                if identity:
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
                        u_fund.is_etf = "true"
                        break

            etf_repo.add_etf_history(ins_code, data, observed_at=iran_time())
            
        db.commit()
        logger.info(f"Successfully updated {len(etf_data)} ETF market prices.")
    except Exception as e:
        db.rollback()
        logger.error(f"Error in ETF market update: {e}")
    finally:
        db.close()