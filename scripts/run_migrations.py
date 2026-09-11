"""Boot-time schema migration runner and data seeder.

Applied at container start (scripts/entrypoint.sh) before uvicorn/worker:
base tables come from the SQLAlchemy models (create_all), then every SQL
file in migrations/ is applied in filename order — each one exactly once,
tracked in the schema_migrations table. Each file runs in its own
transaction, so a failed migration rolls back cleanly and the container
restart retries it.

A Postgres advisory lock serializes concurrent boots: web and worker start
at the same time on a fresh volume and must not apply the same file twice.

After migrations, if the database is empty (fresh volume), a seed snapshot
(seed/dashboard_seed.sql.gz — real TSETMC data collected by this system
itself) is loaded so the dashboard is fully warm from the first second;
live syncs take over from there. The seed is a single transaction and
non-fatal: if it ever fails, the system boots anyway and the live pipeline
warms the database on its own.
"""

import gzip
import glob
import logging
import os
import sys

# اجرای مستقیم این فایل (python scripts/run_migrations.py) دایرکتوری
# scripts را روی sys.path می‌گذارد؛ ریشه پروژه را صریح اضافه می‌کنیم
# تا import های core مستقل از دایرکتوری کاری کار کنند.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg2

from core.database import DATABASE_URL, engine
from core.models import Base

# Arbitrary project-unique lock key for pg_advisory_lock.
LOCK_KEY = 7420001

logging.basicConfig(level=logging.INFO, format="%(asctime)s [migrate] %(levelname)s %(message)s")
logger = logging.getLogger("migrate")

MIGRATIONS_DIR = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "migrations")
)

SEED_FILE = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "seed", "dashboard_seed.sql.gz")
)


def _seed_if_empty(conn) -> None:
    """دیتابیس خالی (ولوم تازه) را با اسنپ‌شات داده واقعی پر می‌کند.

    اسنپ‌شات، داده‌ای است که خود سیستم از TSETMC جمع کرده — نه داده ساختگی —
    و فقط وقتی بارگذاری می‌شود که جدول funds خالی باشد. کل بارگذاری در یک
    تراکنش است: یا کامل می‌نشیند یا هیچ‌چیز؛ و شکست آن کشنده نیست، چون
    خط لوله زنده خودش دیتابیس را گرم می‌کند.
    """
    if os.environ.get("SEED_IF_EMPTY", "1") == "0":
        logger.info("seeding disabled by SEED_IF_EMPTY=0")
        return

    if not os.path.exists(SEED_FILE):
        logger.info("no seed file at %s — skipping", SEED_FILE)
        return

    with conn.cursor() as cur:
        # نام اسکیما صریح است چون خود اسنپ‌شات بعداً search_path را عوض می‌کند.
        cur.execute("SELECT count(*) FROM public.funds")
        (fund_count,) = cur.fetchone()
        if fund_count:
            logger.info("database already has %s funds — seed skipped", fund_count)
            return

        logger.info("empty database — loading seed snapshot %s", SEED_FILE)
        try:
            # کل فایل (SET ها + INSERT ها + setval ها) یک‌جا اجرا می‌شود؛
            # commit در پایان یعنی همه یا هیچ.
            with gzip.open(SEED_FILE, "rt", encoding="utf-8") as handle:
                cur.execute(handle.read())
            conn.commit()
        except Exception:
            conn.rollback()
            logger.exception("seed load failed and was rolled back — live sync will warm the database")
            return

        cur.execute(
            "SELECT (SELECT count(*) FROM public.funds),"
            " (SELECT count(*) FROM public.fund_histories),"
            " (SELECT count(*) FROM public.etf_market),"
            " (SELECT count(*) FROM public.etf_market_histories),"
            " (SELECT count(*) FROM public.benchmark_histories)"
        )
        logger.info("seed loaded: %s funds / %s fund histories / %s ETF rows / %s ETF histories / %s benchmark rows", *cur.fetchone())


def run() -> int:
    # 1) جداول پایه از مدل‌های SQLAlchemy — مهاجرت‌ها فقط آن‌ها را گسترش می‌دهند.
    Base.metadata.create_all(bind=engine)

    files = sorted(glob.glob(os.path.join(MIGRATIONS_DIR, "*.sql")))
    if not files:
        logger.warning("no SQL migrations found in %s", MIGRATIONS_DIR)
        return 0

    conn = psycopg2.connect(DATABASE_URL)
    try:
        with conn.cursor() as cur:
            # وب و کارگر هم‌زمان بوت می‌شوند؛ فقط یک فرآیند مهاجرت را اجرا می‌کند.
            conn.autocommit = True
            cur.execute("SELECT pg_advisory_lock(%s)", (LOCK_KEY,))
            conn.autocommit = False

        newly_applied = 0
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    filename VARCHAR(255) PRIMARY KEY,
                    applied_at TIMESTAMP NOT NULL DEFAULT now()
                )
                """
            )
            conn.commit()
            cur.execute("SELECT filename FROM schema_migrations")
            applied = {row[0] for row in cur.fetchall()}

            for filepath in files:
                filename = os.path.basename(filepath)
                if filename in applied:
                    continue
                with open(filepath, encoding="utf-8") as handle:
                    sql = handle.read()
                logger.info("applying %s", filename)
                try:
                    # هر فایل در تراکنش خودش: یا کامل اعمال می‌شود یا هیچ‌چیز.
                    cur.execute(sql)
                    cur.execute(
                        "INSERT INTO schema_migrations (filename) VALUES (%s)",
                        (filename,),
                    )
                    conn.commit()
                    newly_applied += 1
                except Exception:
                    conn.rollback()
                    logger.exception("migration %s failed and was rolled back", filename)
                    return 1

        # هنوز زیر قفل advisory هستیم: فقط یک فرآیند seed می‌کند.
        _seed_if_empty(conn)

        logger.info(
            "schema up to date: %d file(s) known, %d applied now",
            len(files),
            newly_applied,
        )
        return 0
    finally:
        # بستن اتصال، قفل advisory را هم آزاد می‌کند.
        conn.close()


if __name__ == "__main__":
    sys.exit(run())
