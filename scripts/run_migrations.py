"""Boot-time schema migration runner.

Applied at container start (scripts/entrypoint.sh) before uvicorn/worker:
base tables come from the SQLAlchemy models (create_all), then every SQL
file in migrations/ is applied in filename order — each one exactly once,
tracked in the schema_migrations table. Each file runs in its own
transaction, so a failed migration rolls back cleanly and the container
restart retries it.

A Postgres advisory lock serializes concurrent boots: web and worker start
at the same time on a fresh volume and must not apply the same file twice.
"""

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
