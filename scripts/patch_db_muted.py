import sqlite3

conn = sqlite3.connect('hymns.db')
cursor = conn.cursor()

print("Applying 'Muted' Column Patch...")

try:
    # Add column with default 0 (False)
    cursor.execute("ALTER TABLE program_items ADD COLUMN is_muted BOOLEAN DEFAULT 0")
    print("✅ Added 'is_muted' column.")
except sqlite3.OperationalError as e:
    print(f"ℹ️  Column might already exist: {e}")

conn.commit()
conn.close()