"""
Script to retroactively create review schedules for all submitted exams with incorrect answers
"""
import sqlite3
import json
from datetime import datetime, timedelta

DB_PATH = "database_files/qera.db"

def calculate_next_interval(review_count, ease_factor, previous_interval, quality):
    """SM-2 Algorithm"""
    new_ease = ease_factor + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
    new_ease = max(1.3, min(2.6, new_ease))
    
    if quality < 3:
        next_interval = 1
    elif review_count == 0:
        next_interval = 1
    elif review_count == 1:
        next_interval = 3
    else:
        next_interval = max(1, int(previous_interval * new_ease))
    
    return next_interval, new_ease

def get_next_review_datetime(interval_days):
    """Get ISO format datetime for next review"""
    next_review = datetime.now() + timedelta(days=interval_days)
    return next_review.isoformat()

def main():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    print("Starting review schedule population...\n")
    
    # Get all submitted exam attempts
    cursor.execute("""
        SELECT ea.id, ea.user_id, ea.exam_id, ea.score, ea.total_marks, ea.answers
        FROM exam_attempts ea
        WHERE ea.status = 'submitted'
        ORDER BY ea.submitted_at DESC
    """)
    attempts = cursor.fetchall()
    print(f"Found {len(attempts)} submitted exam attempts\n")
    
    total_reviews_created = 0
    
    for attempt_id, user_id, exam_id, score, total_marks, answers_json in attempts:
        # Get the questions for this exam
        cursor.execute("""
            SELECT q.id, q.correct_answer, eq.marks
            FROM exam_questions eq
            JOIN questions q ON q.id = eq.question_id
            WHERE eq.exam_id = ?
        """, (exam_id,))
        questions = cursor.fetchall()
        
        # Parse answers
        try:
            answers = json.loads(answers_json) if answers_json else {}
        except:
            answers = {}
        
        # Find incorrect answers
        incorrect_questions = []
        for q_id, correct_answer, marks in questions:
            given_answer = str(answers.get(str(q_id), "")).strip()
            expected_answer = str(correct_answer or "").strip()
            
            if given_answer and given_answer.lower() != expected_answer.lower():
                incorrect_questions.append(q_id)
        
        if incorrect_questions:
            print(f"Attempt {attempt_id} (User {user_id}, Exam {exam_id}): {len(incorrect_questions)} incorrect answers")
            
            # Create or update review schedules for each incorrect answer
            for q_id in incorrect_questions:
                # Check if already exists
                cursor.execute(
                    "SELECT id FROM review_schedules WHERE user_id = ? AND question_id = ?",
                    (user_id, q_id)
                )
                existing = cursor.fetchone()
                
                if not existing:
                    # Create new review schedule
                    next_interval, ease_factor = calculate_next_interval(0, 2.5, 0, 2)
                    next_review = get_next_review_datetime(next_interval)
                    
                    cursor.execute("""
                        INSERT INTO review_schedules
                        (user_id, question_id, next_review_at, interval_days, ease_factor, status, source_attempt_id)
                        VALUES (?, ?, ?, ?, ?, 'pending', ?)
                    """, (user_id, q_id, next_review, next_interval, ease_factor, attempt_id))
                    total_reviews_created += 1
                    print(f"  ✓ Created review schedule for question {q_id}")
    
    conn.commit()
    
    # Verify creation
    cursor.execute("SELECT COUNT(*) FROM review_schedules")
    total = cursor.fetchone()[0]
    
    print(f"\n{'='*50}")
    print(f"Total reviews created: {total_reviews_created}")
    print(f"Total review schedules in database: {total}")
    print(f"{'='*50}\n")
    
    # Show reviews by user
    cursor.execute("""
        SELECT u.id, u.name, COUNT(rs.id) as review_count
        FROM review_schedules rs
        JOIN users u ON u.id = rs.user_id
        GROUP BY u.id, u.name
        ORDER BY review_count DESC
    """)
    
    print("Reviews by user:")
    for uid, name, count in cursor.fetchall():
        print(f"  {name} (ID: {uid}): {count} reviews")
    
    conn.close()
    print("\nDone!")

if __name__ == "__main__":
    main()
