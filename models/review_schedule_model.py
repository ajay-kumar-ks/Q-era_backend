"""Review Schedule Model - Handles database operations for review scheduling"""
from typing import Optional
from datetime import datetime

try:
    from backend.services.spaced_repetition_service import (
        calculate_next_interval,
        get_next_review_datetime,
        get_priority_score,
    )
except ImportError:
    from services.spaced_repetition_service import (
        calculate_next_interval,
        get_next_review_datetime,
        get_priority_score,
    )


async def create_or_update_review_schedule(
    db,
    user_id: int,
    question_id: int,
    source_attempt_id: Optional[int] = None,
) -> Optional[dict]:
    """
    Create or update a review schedule for a question that was answered incorrectly.
    Uses SM-2 algorithm to schedule next review.
    """
    # Check if review schedule already exists
    cursor = await db.execute(
        "SELECT id, review_count, interval_days, ease_factor FROM review_schedules WHERE user_id = ? AND question_id = ?",
        (user_id, question_id),
    )
    existing = await cursor.fetchone()

    if existing:
        # Update existing schedule
        review_id, review_count, prev_interval, ease_factor = existing
        next_interval, new_ease = calculate_next_interval(
            review_count=review_count,
            ease_factor=ease_factor,
            previous_interval=prev_interval,
            quality=2,  # Incorrect answer
        )
        next_review = get_next_review_datetime(next_interval)

        await db.execute(
            """UPDATE review_schedules 
               SET next_review_at = ?, interval_days = ?, ease_factor = ?, 
                   updated_at = datetime('now')
               WHERE id = ?""",
            (next_review, next_interval, new_ease, review_id),
        )
    else:
        # Create new schedule
        next_interval, ease_factor = calculate_next_interval(
            review_count=0,
            ease_factor=2.5,
            previous_interval=0,
            quality=2,
        )
        next_review = get_next_review_datetime(next_interval)

        await db.execute(
            """INSERT INTO review_schedules 
               (user_id, question_id, next_review_at, interval_days, ease_factor, source_attempt_id)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (user_id, question_id, next_review, next_interval, ease_factor, source_attempt_id),
        )

    await db.commit()
    return await get_review_schedule(db, user_id, question_id)


async def get_review_schedule(
    db,
    user_id: int,
    question_id: int,
) -> Optional[dict]:
    """Get a specific review schedule"""
    cursor = await db.execute(
        """SELECT id, user_id, question_id, last_reviewed_at, next_review_at,
                  review_count, interval_days, ease_factor, status
           FROM review_schedules
           WHERE user_id = ? AND question_id = ?""",
        (user_id, question_id),
    )
    row = await cursor.fetchone()
    return _row_to_review_schedule(row) if row else None


async def get_due_reviews(
    db,
    user_id: int,
    limit: int = 20,
) -> list[dict]:
    """Get questions due for review for a user, sorted by priority"""
    cursor = await db.execute(
        """SELECT rs.id, rs.user_id, rs.question_id, rs.last_reviewed_at, rs.next_review_at,
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
           LIMIT ?""",
        (user_id, limit),
    )
    rows = await cursor.fetchall()
    return [_row_to_review_with_question(row) for row in rows]


async def get_all_review_schedules(
    db,
    user_id: int,
    status: str = "pending",
    limit: int = 50,
) -> list[dict]:
    """Get all review schedules for a user"""
    cursor = await db.execute(
        """SELECT rs.id, rs.user_id, rs.question_id, rs.last_reviewed_at, rs.next_review_at,
                  rs.review_count, rs.interval_days, rs.ease_factor, rs.status,
                  q.id, q.title, q.description, q.type, q.difficulty, q.correct_answer,
                  COALESCE(GROUP_CONCAT(t.name), '') as tags
           FROM review_schedules rs
           JOIN questions q ON q.id = rs.question_id
           LEFT JOIN question_tags qt ON qt.question_id = q.id
           LEFT JOIN tags t ON t.id = qt.tag_id
           WHERE rs.user_id = ? AND rs.status = ?
           GROUP BY rs.id, q.id
           ORDER BY rs.next_review_at ASC
           LIMIT ?""",
        (user_id, status, limit),
    )
    rows = await cursor.fetchall()
    return [_row_to_review_with_question(row) for row in rows]


async def record_review_attempt(
    db,
    review_schedule_id: int,
    user_id: int,
    question_id: int,
    user_answer: str,
    is_correct: bool,
    time_spent_seconds: int = 0,
) -> dict:
    """Record a review attempt and update the schedule"""
    # Record in history
    await db.execute(
        """INSERT INTO review_history 
           (review_schedule_id, user_id, question_id, user_answer, is_correct, time_spent_seconds)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (review_schedule_id, user_id, question_id, user_answer, int(is_correct), time_spent_seconds),
    )

    # Get current schedule
    cursor = await db.execute(
        """SELECT review_count, interval_days, ease_factor FROM review_schedules 
           WHERE id = ?""",
        (review_schedule_id,),
    )
    row = await cursor.fetchone()
    if not row:
        await db.commit()
        return {}

    review_count, interval_days, ease_factor = row

    # Calculate new schedule based on answer quality
    quality = 5 if is_correct else 2  # 5 = correct, 2 = incorrect
    next_interval, new_ease = calculate_next_interval(
        review_count=review_count,
        ease_factor=ease_factor,
        previous_interval=interval_days,
        quality=quality,
    )

    # Determine new status
    if quality >= 4:  # Correct and confident
        new_status = "completed" if review_count >= 4 else "pending"
    else:
        new_status = "pending"

    next_review = get_next_review_datetime(next_interval)

    # Update schedule
    await db.execute(
        """UPDATE review_schedules
           SET review_count = review_count + 1,
               last_reviewed_at = datetime('now'),
               next_review_at = ?,
               interval_days = ?,
               ease_factor = ?,
               status = ?,
               updated_at = datetime('now')
           WHERE id = ?""",
        (next_review, next_interval, new_ease, new_status, review_schedule_id),
    )

    await db.commit()

    return await get_review_schedule(
        db, user_id, question_id
    ) or {}


async def get_review_statistics(db, user_id: int) -> dict:
    """Get review statistics for a user"""
    cursor = await db.execute(
        """SELECT 
           COUNT(*) as total_scheduled,
           SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) as due_count,
           SUM(CASE WHEN next_review_at <= datetime('now') AND status = 'pending' THEN 1 ELSE 0 END) as overdue_count
           FROM review_schedules
           WHERE user_id = ?""",
        (user_id,),
    )
    row = await cursor.fetchone()
    total, due, overdue = row if row else (0, 0, 0)

    # Get review history stats
    cursor = await db.execute(
        """SELECT
           COUNT(*) as total_reviews,
           SUM(CASE WHEN is_correct = 1 THEN 1 ELSE 0 END) as correct_count
           FROM review_history
           WHERE user_id = ?""",
        (user_id,),
    )
    hist_row = await cursor.fetchone()
    hist_total, hist_correct = hist_row if hist_row else (0, 0)

    return {
        "total_scheduled": total or 0,
        "due_count": due or 0,
        "overdue_count": overdue or 0,
        "total_reviews": hist_total or 0,
        "correct_reviews": hist_correct or 0,
        "review_accuracy": (hist_correct / hist_total * 100) if hist_total else 0.0,
    }


async def get_review_history(
    db,
    user_id: int,
    question_id: Optional[int] = None,
    limit: int = 20,
) -> list[dict]:
    """Get review history for a user or specific question"""
    if question_id:
        cursor = await db.execute(
            """SELECT id, review_schedule_id, user_id, question_id, user_answer,
                      is_correct, time_spent_seconds, reviewed_at
               FROM review_history
               WHERE user_id = ? AND question_id = ?
               ORDER BY reviewed_at DESC
               LIMIT ?""",
            (user_id, question_id, limit),
        )
    else:
        cursor = await db.execute(
            """SELECT id, review_schedule_id, user_id, question_id, user_answer,
                      is_correct, time_spent_seconds, reviewed_at
               FROM review_history
               WHERE user_id = ?
               ORDER BY reviewed_at DESC
               LIMIT ?""",
            (user_id, limit),
        )

    rows = await cursor.fetchall()
    return [
        {
            "id": row[0],
            "review_schedule_id": row[1],
            "user_id": row[2],
            "question_id": row[3],
            "user_answer": row[4],
            "is_correct": bool(row[5]),
            "time_spent_seconds": row[6],
            "reviewed_at": row[7],
        }
        for row in rows
    ]


def _row_to_review_schedule(row) -> dict:
    """Convert database row to review schedule dict"""
    return {
        "id": row[0],
        "user_id": row[1],
        "question_id": row[2],
        "last_reviewed_at": row[3],
        "next_review_at": row[4],
        "review_count": row[5],
        "interval_days": row[6],
        "ease_factor": row[7],
        "status": row[8],
    }


def _row_to_review_with_question(row) -> dict:
    """Convert database row with question data to dict"""
    return {
        "id": row[0],
        "user_id": row[1],
        "question_id": row[2],
        "last_reviewed_at": row[3],
        "next_review_at": row[4],
        "review_count": row[5],
        "interval_days": row[6],
        "ease_factor": row[7],
        "status": row[8],
        "question": {
            "id": row[9],
            "title": row[10],
            "description": row[11],
            "type": row[12],
            "difficulty": row[13],
            "correct_answer": row[14],
            "tags": [tag for tag in (row[15] or "").split(",") if tag],
        },
    }
