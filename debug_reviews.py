"""
Debug script to check review_schedules table and apply migration if needed
"""
import sqlite3
import os

DB_PATH = "database_files/qera.db"
MIGRATIONS_DIR = "database_files/migrations"

def main():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Check if review_schedules table exists
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='review_schedules'"
    )
    result = cursor.fetchone()
    
    if result:
        print("✓ review_schedules table EXISTS")
    else:
        print("✗ review_schedules table NOT FOUND - Applying migration...")
        
        # Read and apply migration
        migration_file = os.path.join(MIGRATIONS_DIR, "0008_add_review_schedules_table.sql")
        if os.path.exists(migration_file):
            with open(migration_file, 'r') as f:
                migration_sql = f.read()
            
            # Split by semicolon and execute each statement
            statements = [stmt.strip() for stmt in migration_sql.split(";") if stmt.strip()]
            for stmt in statements:
                print(f"Executing: {stmt[:60]}...")
                cursor.execute(stmt)
            
            conn.commit()
            print("✓ Migration applied successfully!")
        else:
            print(f"✗ Migration file not found: {migration_file}")
    
    # Check for any exam attempts
    cursor.execute("SELECT COUNT(*) FROM exam_attempts WHERE status = 'submitted'")
    count = cursor.fetchone()
    print(f"\nSubmitted exam attempts: {count[0]}")
    
    # Check for review_schedules
    cursor.execute("SELECT COUNT(*) FROM review_schedules")
    count = cursor.fetchone()
    print(f"Review schedules created: {count[0]}")
    
    # Check for any users
    cursor.execute("SELECT id, name FROM users LIMIT 5")
    users = cursor.fetchall()
    print(f"\nUsers in database:")
    for uid, name in users:
        print(f"  ID: {uid}, Name: {name}")
        
        # Check their exam attempts
        cursor.execute(
            "SELECT id, exam_id, score, status FROM exam_attempts WHERE user_id = ? LIMIT 3",
            (uid,)
        )
        attempts = cursor.fetchall()
        for aid, eid, score, status in attempts:
            print(f"    Attempt {aid}: Exam {eid}, Score {score}, Status {status}")
            
            # Check their reviews for this attempt
            cursor.execute(
                "SELECT COUNT(*) FROM review_schedules WHERE user_id = ? AND source_attempt_id = ?",
                (uid, aid)
            )
            review_count = cursor.fetchone()
            print(f"      Reviews created from this attempt: {review_count[0]}")
    
    conn.close()
    print("\nDebug complete!")

if __name__ == "__main__":
    main()
