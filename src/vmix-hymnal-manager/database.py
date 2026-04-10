import logging
import sqlite3
from typing import List, Tuple, Callable

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from config import settings

logger = logging.getLogger(__name__)

engine = create_engine(
    settings.DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """Dependency injection for database sessions."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def reconnect(db_url: str):
    """Dispose current engine and reconnect to a different database."""
    global engine
    engine.dispose()
    engine = create_engine(db_url, connect_args={"check_same_thread": False})
    SessionLocal.configure(bind=engine)
    Base.metadata.create_all(bind=engine)


# Raw SQL table definitions matching models.py — used for creating a new DB
# at a custom path without importing the full ORM (like patch_db_settings.py).
_TABLE_SQL = [
    """CREATE TABLE IF NOT EXISTS hymns (
        id INTEGER PRIMARY KEY,
        number VARCHAR,
        title VARCHAR
    )""",
    """CREATE TABLE IF NOT EXISTS slides (
        id INTEGER PRIMARY KEY,
        hymn_id INTEGER REFERENCES hymns(id),
        label VARCHAR,
        content TEXT,
        "order" INTEGER,
        type VARCHAR DEFAULT 'VMIX'
    )""",
    """CREATE TABLE IF NOT EXISTS service_plan (
        id INTEGER PRIMARY KEY,
        sequence INTEGER UNIQUE,
        hymn_id INTEGER REFERENCES hymns(id)
    )""",
    """CREATE TABLE IF NOT EXISTS programs (
        id INTEGER PRIMARY KEY,
        name VARCHAR,
        is_active BOOLEAN DEFAULT 0,
        template_id INTEGER REFERENCES presentation_templates(id),
        last_used DATETIME
    )""",
    """CREATE TABLE IF NOT EXISTS program_items (
        id INTEGER PRIMARY KEY,
        program_id INTEGER REFERENCES programs(id),
        sequence INTEGER,
        title VARCHAR,
        subtitle VARCHAR,
        tag VARCHAR,
        is_muted BOOLEAN DEFAULT 0
    )""",
    """CREATE TABLE IF NOT EXISTS presentation_templates (
        id INTEGER PRIMARY KEY,
        name VARCHAR,
        filename VARCHAR
    )""",
    """CREATE TABLE IF NOT EXISTS data_tables (
        id INTEGER PRIMARY KEY,
        name VARCHAR,
        slug VARCHAR UNIQUE,
        columns_json TEXT DEFAULT '[]',
        created_at DATETIME,
        updated_at DATETIME
    )""",
    """CREATE TABLE IF NOT EXISTS data_table_rows (
        id INTEGER PRIMARY KEY,
        table_id INTEGER REFERENCES data_tables(id),
        sequence INTEGER,
        data_json TEXT DEFAULT '{}'
    )""",
    """CREATE TABLE IF NOT EXISTS app_settings (
        key VARCHAR PRIMARY KEY,
        value VARCHAR
    )""",
]


def init_db_at(db_path: str):
    """Create a new database with all tables at the given path (raw SQLite)."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    for sql in _TABLE_SQL:
        cursor.execute(sql)
    # Mark fresh databases at the current app version
    cursor.execute(
        "INSERT OR REPLACE INTO app_settings (key, value) VALUES (?, ?)",
        ("schema_version", settings.APP_VERSION),
    )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Versioned migrations
# ---------------------------------------------------------------------------

def _migrate_1_0_0(conn: sqlite3.Connection):
    """Baseline — ensure all v1.0.0 tables and columns exist."""
    cursor = conn.cursor()
    for sql in _TABLE_SQL:
        cursor.execute(sql)

    # Columns that may be missing on pre-versioning databases
    cursor.execute("PRAGMA table_info(data_tables)")
    cols = [r[1] for r in cursor.fetchall()]
    if "updated_at" not in cols:
        cursor.execute("ALTER TABLE data_tables ADD COLUMN updated_at DATETIME")
        cursor.execute(
            "UPDATE data_tables SET updated_at = created_at WHERE updated_at IS NULL"
        )


# Ordered list of migrations: (version, description, function)
MIGRATIONS: List[Tuple[str, str, Callable]] = [
    ("1.0.0", "baseline schema", _migrate_1_0_0),
]


def _version_tuple(v: str):
    """Convert '1.2.3' or '1.2.3a' to a comparable tuple.

    Strips non-numeric suffixes (e.g. 'a', 'b', 'rc1') from each part
    so that '1.0.0a' compares equal to '1.0.0' for migration purposes.
    """
    import re
    return tuple(int(re.sub(r"[^0-9].*", "", x)) for x in v.split("."))


def get_schema_version(db_path: str) -> str:
    """Read the current schema version from a database."""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT value FROM app_settings WHERE key = 'schema_version'"
        )
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else "0.0.0"
    except Exception:
        return "0.0.0"


def apply_migrations(db_path: str):
    """Run all pending migrations on the given database."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Ensure app_settings exists (bootstrap for pre-versioning databases)
    cursor.execute(
        "CREATE TABLE IF NOT EXISTS app_settings "
        "(key VARCHAR PRIMARY KEY, value VARCHAR)"
    )
    conn.commit()

    cursor.execute(
        "SELECT value FROM app_settings WHERE key = 'schema_version'"
    )
    row = cursor.fetchone()
    current = row[0] if row else "0.0.0"
    current_tuple = _version_tuple(current)

    applied = 0
    for version, description, migrate_fn in MIGRATIONS:
        if _version_tuple(version) > current_tuple:
            logger.info("Applying migration %s: %s", version, description)
            migrate_fn(conn)
            cursor.execute(
                "INSERT OR REPLACE INTO app_settings (key, value) VALUES (?, ?)",
                ("schema_version", version),
            )
            conn.commit()
            applied += 1

    if applied:
        logger.info("Applied %d migration(s), now at schema version %s",
                     applied, version)
    else:
        logger.info("Database at schema version %s — up to date", current)

    conn.close()
