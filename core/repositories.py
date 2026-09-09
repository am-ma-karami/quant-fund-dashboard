from sqlalchemy.orm import Session
from sqlalchemy import text
from core.models import Fund, FundHistory, HistoryBackfillState, ETFMarket, ETFMarketHistory, BenchmarkHistory
from services.risk import returns_from_prices, annualized_volatility, sharpe_ratio, maximum_drawdown
from datetime import datetime
from sqlalchemy.dialects.postgresql import insert as pg_insert

from zoneinfo import ZoneInfo

def iran_time():
    return datetime.now(ZoneInfo("Asia/Tehran")).replace(tzinfo=None)

class FundRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_fund_by_reg_no(self, reg_no: int):
        return self.db.query(Fund).filter(Fund.reg_no == reg_no).first()

    def get_funds_by_type(self, type_id: int):
        return self.db.query(Fund).filter(Fund.fund_type == type_id).order_by(Fund.net_asset.desc()).all()

    def get_top_funds_by_return(self, limit: int = 10):
        # Show top funds across all types that have return data
        return self.db.query(Fund).filter(
            Fund.day30_return != None
        ).order_by(Fund.day30_return.desc()).limit(limit).all()

    def get_fund_history(self, reg_no: int, limit: int = 30, since: datetime | None = None):
        query = self.db.query(FundHistory).filter(FundHistory.fund_reg_no == reg_no)
        if since is not None:
            query = query.filter(FundHistory.observed_at >= since)
        rows = (
            query
            .order_by(
                FundHistory.observed_at.desc()
            )
            .limit(limit)
            .all()
        )

        return list(reversed(rows))

    def upsert_fund(self, reg_no: int, name: str, fund_type: int, clean_data: dict):
        """بروزرسانی یا ساخت صندوق جدید (Upsert)"""
        fund = self.get_fund_by_reg_no(reg_no)
        if not fund:
            fund = Fund(reg_no=reg_no, name=name, fund_type=fund_type)
            self.db.add(fund)
            self.db.flush()
            
        fund.nav_stat = clean_data['nav_stat']
        fund.nav_sub = clean_data['nav_sub']
        fund.nav_red = clean_data['nav_red']
        fund.net_asset = clean_data['net_asset']
        fund.units = clean_data['units']
        fund.manager = clean_data['manager']
        fund.day30_return = clean_data['day30_return']
        fund.day90_return = clean_data['day90_return']
        fund.day365_return = clean_data['day365_return']
        fund.day1_return = clean_data['day1_return']
        fund.day7_return = clean_data['day7_return']
        fund.day180_return = clean_data['day180_return']
        fund.portfolio_stock = clean_data['portfolio_stock']
        fund.portfolio_bond = clean_data['portfolio_bond']
        fund.portfolio_cash = clean_data['portfolio_cash']
        fund.portfolio_other = clean_data['portfolio_other']
        fund.fund_type = fund_type
        fund.last_updated = iran_time()
        return fund

    def add_fund_history(
        self,
        reg_no: int,
        nav_stat: float,
        net_asset: float,
        observed_at=None,
        nav_sub: float = None,
        nav_red: float = None,
        units: float = None,
    ):
        history = FundHistory(
            fund_reg_no=reg_no,
            nav_stat=nav_stat,
            nav_sub=nav_sub,
            nav_red=nav_red,
            net_asset=net_asset,
            units=units,
            observed_at=observed_at or iran_time()
        )
        self.db.add(history)

    def get_heatmap_data(self, limit: int = 50):
        """دریافت دیتای صندوق‌های بزرگ برای نقشه حرارتی"""
        # فقط صندوق‌هایی که دیتای Asset و Return دارند را می‌گیریم
        return self.db.query(Fund).filter(
            Fund.net_asset > 0,
            Fund.day30_return != None
        ).order_by(Fund.net_asset.desc()).limit(limit).all()

    def get_all_funds_for_screener(self):
        """دریافت تمام صندوق‌ها برای صفحه فیلترنویسی"""
        return self.db.query(Fund).filter(Fund.net_asset > 0).all()

    def get_latest_observation_time(self, reg_no: int):
        """گرفتن آخرین زمان دیتای ثبت شده برای یک صندوق"""
        latest = self.db.query(FundHistory).filter(FundHistory.fund_reg_no == reg_no)\
                        .order_by(FundHistory.observed_at.desc()).first()
        return latest.observed_at if latest else None

    def get_latest_history_before(self, reg_no: int, before: datetime):
        """Get the last NAV known before a chart window begins."""
        return (
            self.db.query(FundHistory)
            .filter(
                FundHistory.fund_reg_no == reg_no,
                FundHistory.observed_at < before,
            )
            .order_by(FundHistory.observed_at.desc())
            .first()
        )

    def has_history(self, reg_no: int) -> bool:
        return (
            self.db.query(FundHistory.id)
            .filter(FundHistory.fund_reg_no == reg_no)
            .first()
            is not None
        )

    def get_history_count(self, reg_no: int, since: datetime | None = None) -> int:
        query = self.db.query(FundHistory).filter(FundHistory.fund_reg_no == reg_no)
        if since is not None:
            query = query.filter(FundHistory.observed_at >= since)
        return query.count()

    def get_history_backfill_progress(
        self, target_records: int, since: datetime | None = None
    ) -> tuple[int, int]:
        """Return the number of eligible funds that reached the target and their total."""
        from sqlalchemy import func

        history_query = self.db.query(
                FundHistory.fund_reg_no,
                func.count(FundHistory.id).label("hist_count"),
            )
        if since is not None:
            history_query = history_query.filter(FundHistory.observed_at >= since)
        counts = history_query.group_by(FundHistory.fund_reg_no).subquery()
        eligible = self.db.query(Fund).filter(Fund.net_asset > 0)
        total = eligible.count()
        complete = (
            eligible.outerjoin(counts, Fund.reg_no == counts.c.fund_reg_no)
            .filter(func.coalesce(counts.c.hist_count, 0) >= target_records)
            .count()
        )
        return complete, total

    def get_next_history_backfill_fund(
        self,
        initial_records: int,
        target_records: int,
        since: datetime | None = None,
        skip_checked_since: datetime | None = None,
    ) -> tuple[Fund | None, str | None]:
        """Prioritize initial coverage for every fund before completing full history."""
        from sqlalchemy import func

        history_query = self.db.query(
                FundHistory.fund_reg_no,
                func.count(FundHistory.id).label("hist_count"),
            )
        if since is not None:
            history_query = history_query.filter(FundHistory.observed_at >= since)
        counts = history_query.group_by(FundHistory.fund_reg_no).subquery()
        base_query = self.db.query(Fund).outerjoin(
            counts, Fund.reg_no == counts.c.fund_reg_no
        ).outerjoin(
            HistoryBackfillState, Fund.reg_no == HistoryBackfillState.fund_reg_no
        ).filter(Fund.net_asset > 0)
        if skip_checked_since is not None:
            base_query = base_query.filter(
                (HistoryBackfillState.checked_at.is_(None))
                | (HistoryBackfillState.checked_at < skip_checked_since)
            )
        history_count = func.coalesce(counts.c.hist_count, 0)
        order_by = (history_count.asc(), Fund.net_asset.desc())

        fund = base_query.filter(history_count < initial_records).order_by(*order_by).first()
        if fund:
            return fund, "initial"

        fund = base_query.filter(history_count < target_records).order_by(*order_by).first()
        return (fund, "full") if fund else (None, None)

    def mark_history_source_stale(self, reg_no: int) -> None:
        state = self.db.get(HistoryBackfillState, reg_no)
        if state is None:
            self.db.add(HistoryBackfillState(fund_reg_no=reg_no, checked_at=iran_time()))
        else:
            state.checked_at = iran_time()

    def get_history_by_date(self, reg_no: int, observed_at: datetime):
        return (
            self.db.query(FundHistory)
            .filter(
                FundHistory.fund_reg_no == reg_no,
                FundHistory.observed_at == observed_at
            )
            .first()
        )

    def get_fund_risk_metrics(self, reg_no: int):
        """محاسبه معیارهای ریسک از آخرین 252 observation معتبر NAV صندوق."""
        histories = (
            self.db.query(FundHistory)
            .filter(FundHistory.fund_reg_no == reg_no)
            .order_by(FundHistory.observed_at.desc())
            .limit(252)
            .all()
        )

        histories.reverse()

        if len(histories) < 2:
            return {
                "volatility": None,
                "sharpe_ratio": None,
                "max_drawdown": None,
            }

        prices = [h.nav_stat for h in histories if h.nav_stat is not None and h.nav_stat > 0]

        if len(prices) < 2:
            return {
                "volatility": None,
                "sharpe_ratio": None,
                "max_drawdown": None,
            }

        returns = returns_from_prices(prices)

        return {
            "volatility": annualized_volatility(returns),
            "sharpe_ratio": sharpe_ratio(returns),
            "max_drawdown": maximum_drawdown(prices),
        }

    def get_volatility_map(self, since: datetime) -> dict:
        """نوسان سالانه‌شده هر صندوق از تاریخچه اخیر — در یک کوئری.

        برای نقشه ریسک/بازده داشبورد: به جای ۵۰۰ کوئری جداگانه،
        همه تاریخچه‌ها یکجا خوانده و در پایتون گروه‌بندی می‌شوند.
        """
        rows = (
            self.db.query(
                FundHistory.fund_reg_no,
                FundHistory.nav_stat,
            )
            .filter(
                FundHistory.observed_at >= since,
                FundHistory.nav_stat.isnot(None),
            )
            .order_by(
                FundHistory.fund_reg_no,
                FundHistory.observed_at,
            )
            .all()
        )

        prices_by_fund = {}
        for reg_no, nav in rows:
            if nav is None or nav <= 0:
                continue
            prices_by_fund.setdefault(reg_no, []).append(nav)

        return {
            reg_no: annualized_volatility(returns_from_prices(prices))
            for reg_no, prices in prices_by_fund.items()
        }

    def get_funds_with_insufficient_history(self, min_days: int = 5, limit: int = 20):
        """صندوق‌هایی که تاریخچه ندارند یا آخرین رکوردشان قدیمی است"""
        from datetime import timedelta
        from sqlalchemy import func
        cutoff_date = datetime.utcnow() - timedelta(days=min_days)
        
        # Subquery: history count and latest date per fund
        subq = (
            self.db.query(
                FundHistory.fund_reg_no,
                func.count(FundHistory.id).label('hist_count'),
                func.max(FundHistory.observed_at).label('latest_date')
            )
            .group_by(FundHistory.fund_reg_no)
            .subquery()
        )
        
        # Funds with no history OR latest record older than min_days
        # Prioritize: no history first, then few records, then by net_asset
        return (
            self.db.query(Fund)
            .outerjoin(subq, Fund.reg_no == subq.c.fund_reg_no)
            .filter(
                Fund.net_asset > 0,
                (subq.c.latest_date < cutoff_date) | (subq.c.latest_date.is_(None))
            )
            .order_by(
                subq.c.hist_count.asc().nullsfirst(),  # No history first
                Fund.net_asset.desc()  # Then by size
            )
            .limit(limit)
            .all()
        )

    def upsert_fund_history(
        self,
        reg_no: int,
        nav_stat: float,
        net_asset: float,
        observed_at: datetime,
        nav_sub: float = None,
        nav_red: float = None,
        units: float = None,
    ):
        """
        استفاده از قابلیت بومی PostgreSQL برای سرعت بی‌نهایت و جلوگیری از ارور Duplicate Key
        """
        stmt = pg_insert(FundHistory).values(
            fund_reg_no=reg_no,
            nav_stat=nav_stat,
            nav_sub=nav_sub,
            nav_red=nav_red,
            net_asset=net_asset,
            units=units,
            observed_at=observed_at
        )

        # اگر رکورد با این تاریخ قبلاً وجود داشت، فقط مقادیر آن را آپدیت کن
        stmt = stmt.on_conflict_do_update(
            index_elements=['fund_reg_no', 'observed_at'],
            set_=dict(
                nav_stat=stmt.excluded.nav_stat,
                nav_sub=stmt.excluded.nav_sub,
                nav_red=stmt.excluded.nav_red,
                net_asset=stmt.excluded.net_asset,
                units=stmt.excluded.units,
            )
        )

        self.db.execute(stmt)


class ETFRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_all_etfs(self):
        return self.db.query(ETFMarket).order_by(ETFMarket.total_trades.desc()).all()

    def upsert_etf_market(self, ins_code: str, symbol: str, name: str, data: dict):
        etf = self.db.query(ETFMarket).filter(ETFMarket.ins_code == ins_code).first()
        if not etf:
            etf = ETFMarket(ins_code=ins_code, symbol=symbol, name=name)
            self.db.add(etf)

        etf.last_price = data.get('last_price')
        etf.closing_price = data.get('closing_price')
        etf.price_change = data.get('price_change')
        etf.total_trades = data.get('total_trades')
        etf.total_volume = data.get('total_volume')
        etf.total_value = data.get('total_value')
        etf.price_min = data.get('price_min')
        etf.price_max = data.get('price_max')
        etf.price_first = data.get('price_first')
        etf.price_yesterday = data.get('price_yesterday')
        etf.nav = data.get('nav')
        etf.nav_red = data.get('nav_red')
        etf.nav_sub = data.get('nav_sub')
        etf.premium_discount = data.get('premium_discount')
        etf.last_updated = iran_time()
        return etf

    def add_etf_history(
        self,
        ins_code: str,
        data: dict,
        observed_at=None,
    ):
        history = ETFMarketHistory(
            ins_code=ins_code,
            last_price=data.get('last_price'),
            closing_price=data.get('closing_price'),
            price_change=data.get('price_change'),
            total_trades=data.get('total_trades'),
            total_volume=data.get('total_volume'),
            total_value=data.get('total_value'),
            price_min=data.get('price_min'),
            price_max=data.get('price_max'),
            price_first=data.get('price_first'),
            price_yesterday=data.get('price_yesterday'),
            nav=data.get('nav'),
            nav_red=data.get('nav_red'),
            nav_sub=data.get('nav_sub'),
            premium_discount=data.get('premium_discount'),
            observed_at=observed_at or iran_time()
        )
        self.db.add(history)

    def get_etf_by_ins_code(self, ins_code: str):
        return self.db.query(ETFMarket).filter(ETFMarket.ins_code == ins_code).first()

    def get_etf_history(self, ins_code: str, limit: int = 90):
        rows = (
            self.db.query(ETFMarketHistory)
            .filter(ETFMarketHistory.ins_code == ins_code)
            .order_by(ETFMarketHistory.observed_at.desc())
            .limit(limit)
            .all()
        )

        return list(reversed(rows))


    def get_recent_premiums(
        self,
        ins_code: str,
        limit: int = 60,
    ) -> list[float]:
        rows = (
            self.db.query(
                ETFMarketHistory.premium_discount
            )
            .filter(
                ETFMarketHistory.ins_code == ins_code,
                ETFMarketHistory.premium_discount.isnot(None),
            )
            .order_by(
                ETFMarketHistory.observed_at.desc()
            )
            .limit(limit)
            .all()
        )

        return [
            row[0]
            for row in reversed(rows)
        ]


    def get_daily_price_history(
        self,
        ins_code: str,
        days: int = 90,
    ) -> list:
        """آخرین مشاهده هر روز معاملاتی (برای سری روزانه قیمت/پریمیوم).

        از DISTINCT ON بومی Postgres استفاده می‌کند تا از میان
        ردیف‌های intraday (هر دقیقه در ساعات معاملات)، فقط آخرین
        مشاهده هر روز برداشته شود.
        """
        sql = text(
            """
            SELECT DISTINCT ON (ins_code, observed_at::date)
                   id, ins_code, last_price, closing_price,
                   premium_discount, nav, observed_at
            FROM etf_market_histories
            WHERE ins_code = :ins_code
            ORDER BY ins_code, observed_at::date DESC, observed_at DESC
            LIMIT :limit
            """
        )

        rows = self.db.execute(
            sql,
            {"ins_code": ins_code, "limit": days},
        ).all()

        return list(reversed(rows))

    def get_market_pulse(self):
        """
        محاسبه شاخص‌های کلان بازار (Market Pulse) بر اساس تابلوی لایو ETFها
        """
        etfs = self.db.query(ETFMarket).all()
        total = len(etfs)
        
        if total == 0:
            return {"total": 0, "positive": 0, "negative": 0, "unchanged": 0, 
                    "total_trades": 0, "breadth": 0, "up_volume_ratio": 0}

        positive = sum(1 for e in etfs if (e.price_change or 0) > 0)
        negative = sum(1 for e in etfs if (e.price_change or 0) < 0)
        unchanged = total - positive - negative
        
        # مجموع کل معاملات انجام شده در بازار
        total_trades = sum((e.total_trades or 0) for e in etfs)
        
        # معاملاتی که روی صندوق‌های مثبت انجام شده (Up Volume Proxy)
        up_trades = sum((e.total_trades or 0) for e in etfs if (e.price_change or 0) > 0)
        
        # محاسبه Breadth (درصد صندوق‌های مثبت نسبت به کل)
        breadth = (positive / total) * 100
        
        # محاسبه Up Volume Ratio
        up_volume_ratio = (up_trades / total_trades) * 100 if total_trades > 0 else 0
        
        return {
            "total": total,
            "positive": positive,
            "negative": negative,
            "unchanged": unchanged,
            "total_trades": total_trades,
            "breadth": round(breadth, 1),
            "up_volume_ratio": round(up_volume_ratio, 1)
        }


class BenchmarkRepository:
    def __init__(self, db: Session):
        self.db = db

    def upsert_history(
        self,
        benchmark_code: str,
        benchmark_name: str,
        value: float,
        observed_at: datetime,
    ):
        stmt = pg_insert(BenchmarkHistory).values(
            benchmark_code=benchmark_code,
            benchmark_name=benchmark_name,
            value=value,
            observed_at=observed_at,
        )

        stmt = stmt.on_conflict_do_update(
            index_elements=[
                "benchmark_code",
                "observed_at",
            ],
            set_=dict(
                value=stmt.excluded.value,
                benchmark_name=stmt.excluded.benchmark_name,
            ),
        )

        self.db.execute(stmt)

    def get_history(
        self,
        benchmark_code: str,
        limit: int = 252,
    ):
        """آخرین `limit` مشاهده شاخص به ترتیب صعودی تاریخ."""
        rows = (
            self.db.query(BenchmarkHistory)
            .filter(
                BenchmarkHistory.benchmark_code == benchmark_code
            )
            .order_by(BenchmarkHistory.observed_at.desc())
            .limit(limit)
            .all()
        )

        return list(reversed(rows))
