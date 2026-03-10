import os
import sqlite3
import sys


def resolve_db_path():
    """Resolve the actual database path, checking app_settings for custom path."""
    explicit = sys.argv[1] if len(sys.argv) > 1 else None
    if explicit:
        return explicit

    default_db = 'hymns.db'
    if not os.path.exists(default_db):
        return default_db

    # Check if a custom db_path is configured in app_settings
    try:
        conn = sqlite3.connect(default_db)
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM app_settings WHERE key = 'db_path'")
        row = cursor.fetchone()
        conn.close()
        if row and row[0] and os.path.exists(row[0]):
            return row[0]
    except Exception:
        pass

    return default_db


db_path = resolve_db_path()
if not os.path.exists(db_path):
    print(f"Database not found: {db_path}")
    sys.exit(1)

print(f"Patching database: {os.path.abspath(db_path)}")
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

print("Applying patch: create data_tables and data_table_rows tables ...")

cursor.execute("""
    CREATE TABLE IF NOT EXISTS data_tables (
        id INTEGER PRIMARY KEY,
        name VARCHAR,
        slug VARCHAR UNIQUE,
        columns_json TEXT DEFAULT '[]',
        created_at DATETIME,
        updated_at DATETIME
    )
""")

# Add updated_at column if table already existed without it
cursor.execute("PRAGMA table_info(data_tables)")
columns = [row[1] for row in cursor.fetchall()]
if "updated_at" not in columns:
    print("  Adding updated_at column to data_tables ...")
    cursor.execute("ALTER TABLE data_tables ADD COLUMN updated_at DATETIME")
    cursor.execute("UPDATE data_tables SET updated_at = created_at WHERE updated_at IS NULL")

cursor.execute("""
    CREATE TABLE IF NOT EXISTS data_table_rows (
        id INTEGER PRIMARY KEY,
        table_id INTEGER REFERENCES data_tables(id),
        sequence INTEGER,
        data_json TEXT DEFAULT '{}'
    )
""")

conn.commit()
conn.close()
print("Done!")
