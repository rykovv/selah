import sqlite3

conn = sqlite3.connect('hymns.db')
cursor = conn.cursor()

print("Applying patch: drop UNIQUE constraint on hymns.number ...")

# Check if the unique constraint actually exists
cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='hymns'")
row = cursor.fetchone()
if row is None:
    print("No 'hymns' table found — nothing to do.")
    conn.close()
    exit()

ddl = row[0]
if "unique" not in ddl.lower() and "UNIQUE" not in ddl:
    # Also check for a unique index on number
    cursor.execute("""
        SELECT sql FROM sqlite_master
        WHERE type='index' AND tbl_name='hymns' AND sql LIKE '%UNIQUE%'
    """)
    if not cursor.fetchone():
        print("No UNIQUE constraint on hymns.number — already patched.")
        conn.close()
        exit()

# SQLite doesn't support ALTER TABLE DROP CONSTRAINT.
# We must recreate the table without the unique constraint.

cursor.execute("PRAGMA foreign_keys = OFF")

try:
    # Clean up leftover from a previous failed run
    cursor.execute("DROP TABLE IF EXISTS hymns_old")

    # 1. Rename old table
    cursor.execute("ALTER TABLE hymns RENAME TO hymns_old")

    # 2. Create new table without UNIQUE on number
    cursor.execute("""
        CREATE TABLE hymns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            number VARCHAR,
            title VARCHAR
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS ix_hymns_number ON hymns (number)")

    # 3. Copy data
    cursor.execute("INSERT INTO hymns (id, number, title) SELECT id, number, title FROM hymns_old")

    # 4. Drop old table
    cursor.execute("DROP TABLE hymns_old")

    conn.commit()
    print("Done! UNIQUE constraint removed from hymns.number.")
except Exception as e:
    conn.rollback()
    print(f"Error: {e}")
finally:
    cursor.execute("PRAGMA foreign_keys = ON")
    conn.close()
