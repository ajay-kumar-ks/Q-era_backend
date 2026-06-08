"""Debug the review query"""
import sqlite3

DB_PATH = "database_files/qera.db"
conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

user_id = 14

# Check the exact query
print("Testing the query for user 14:")
cursor.execute("""
    SELECT rs.id, rs.next_review_at, datetime('now') as current_time,
           CASE WHEN rs.next_review_at <= datetime('now') THEN 'YES - DUE' ELSE 'NO - NOT DUE' END as is_due
    FROM review_schedules rs
    WHERE rs.user_id = ?
""", (user_id,))

print("\nReview schedules for user 14:")
for rid, next_review, current_time, is_due in cursor.fetchall():
    print(f"  Review {rid}: Due={next_review} | Now={current_time} | {is_due}")

# Test the actual query used by backend
print("\n\nActual query result (from backend):")
cursor.execute("""
    SELECT rs.id, rs.user_id, rs.question_id, rs.last_reviewed_at, rs.next_review_at,
           rs.review_count, rs.interval_days, rs.ease_factor, rs.status,
           q.id, q.title, q.description, q.type, q.difficulty, q.correct_answer,
           COALESCE(GROUP_CONCAT(t.name), '') as tags
    FROM review_schedules rs
    JOIN questions q ON q.id = rs.question_id
    LEFT JOIN question_tags qt ON qt.question_id = q.id
    LEFT JOIN tags t ON t.id = qt.tag_id
    WHERE rs.user_id = ? AND rs.status = 'pending' AND rs.next_review_at <= datetime('now')
    GROUP BY rs.id, q.id
    ORDER BY rs.next_review_at ASC, rs.ease_factor ASC
    LIMIT 20
""", (user_id,))

rows = cursor.fetchall()
print(f"Found {len(rows)} results")
for row in rows:
    print(f"  Review {row[0]}: Question {row[2]} - {row[10]}")

conn.close()
