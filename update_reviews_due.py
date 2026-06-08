"""Update all pending reviews to be due now"""
import sqlite3

DB_PATH = "database_files/qera.db"
conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# Update all pending reviews to be due now
cursor.execute("UPDATE review_schedules SET next_review_at = datetime('now') WHERE status = 'pending'")
conn.commit()

print(f"✓ Updated {cursor.rowcount} reviews to be due immediately\n")

# Show updated reviews
cursor.execute("SELECT id, user_id, question_id, next_review_at FROM review_schedules ORDER BY user_id")
print("Current review schedules:")
for row in cursor.fetchall():
    print(f"  Review {row[0]}: User {row[1]}, Question {row[2]} - Due: {row[3]}")

conn.close()
print("\n✓ All pending reviews are now due!")
