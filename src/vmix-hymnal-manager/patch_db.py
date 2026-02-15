import sqlite3

# Connect to your database
# Make sure the name matches your actual file (e.g. hymns.db)
conn = sqlite3.connect('hymns.db') 
cursor = conn.cursor()

print("Applying database patch...")

# 1. Add 'template_id' to 'programs' table
try:
    cursor.execute("ALTER TABLE programs ADD COLUMN template_id INTEGER REFERENCES presentation_templates(id)")
    print("✅ Added 'template_id' column to 'programs'.")
except sqlite3.OperationalError as e:
    print(f"ℹ️  'template_id' might already exist: {e}")

# 2. Add 'tag' to 'program_items' table
try:
    cursor.execute("ALTER TABLE program_items ADD COLUMN tag VARCHAR")
    print("✅ Added 'tag' column to 'program_items'.")
except sqlite3.OperationalError as e:
    print(f"ℹ️  'tag' might already exist: {e}")

# 3. Create the new 'presentation_templates' table 
# (SQLAlchemy usually does this, but we can double check)
try:
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS presentation_templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name VARCHAR,
            filename VARCHAR
        )
    """)
    print("✅ Ensured 'presentation_templates' table exists.")
except sqlite3.OperationalError as e:
    print(f"⚠️ Error creating table: {e}")

conn.commit()
conn.close()
print("Done! Restart your app now.")