"""Check current user and their reviews"""
import sqlite3

DB_PATH = "database_files/qera.db"
conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# Find user "ajay"
cursor.execute("SELECT id, name, email FROM users WHERE name LIKE '%ajay%' OR email LIKE '%ajay%'")
users = cursor.fetchall()

print("Users matching 'ajay':")
for uid, name, email in users:
    print(f"  ID {uid}: {name} ({email})")

# Check reviews for each user
print("\nReview schedules by user:")
cursor.execute("SELECT user_id, COUNT(*) as count FROM review_schedules GROUP BY user_id ORDER BY user_id")
for uid, count in cursor.fetchall():
    cursor.execute("SELECT name FROM users WHERE id = ?", (uid,))
    user_name = cursor.fetchone()[0]
    print(f"  User {uid} ({user_name}): {count} reviews")

# Show ALL users
print("\nAll users in database:")
cursor.execute("SELECT id, name, email FROM users ORDER BY id")
for uid, name, email in cursor.fetchall():
    print(f"  ID {uid}: {name} ({email})")

conn.close()
