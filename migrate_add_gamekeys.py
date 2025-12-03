import sqlite3

db = "database.db"

try:
    conn = sqlite3.connect(db)
    cur = conn.cursor()

    cur.execute("ALTER TABLE users ADD COLUMN game_keys TEXT")
    conn.commit()

    print("✔️ Spalte 'game_keys' wurde hinzugefügt.")

except Exception as e:
    print("⚠️ Spalte 'game_keys' konnte nicht hinzugefügt werden:", e)

finally:
    conn.close()
