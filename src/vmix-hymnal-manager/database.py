import sqlite3

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from config import settings

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
    conn.commit()
    conn.close()
