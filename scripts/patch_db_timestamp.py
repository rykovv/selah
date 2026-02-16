import sqlite3
import datetime

conn = sqlite3.connect('hymns.db')
cursor = conn.cursor()

print("Applying Timestamp Patch...")

# 1. Add 'last_used' column
try:
    # We default existing rows to the current time so they aren't Null
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute(f"ALTER TABLE programs ADD COLUMN last_used TIMESTAMP DEFAULT '{now}'")
    print("✅ Added 'last_used' column.")
except sqlite3.OperationalError as e:
    print(f"ℹ️  Column might already exist: {e}")

conn.commit()
conn.close()