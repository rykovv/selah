import sqlite3

conn = sqlite3.connect('hymns.db')
cursor = conn.cursor()

print("Applying patch: create app_settings table ...")

cursor.execute("""
    CREATE TABLE IF NOT EXISTS app_settings (
        key VARCHAR PRIMARY KEY,
        value VARCHAR
    )
""")

conn.commit()
conn.close()
print("Done!")
