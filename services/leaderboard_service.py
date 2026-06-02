from typing import Any, Dict, List

try:
    from backend.models import leaderboard_model
except ImportError:
    from models import leaderboard_model


async def insert_leaderboard_entry(
    db,
    exam_id: int,
    user_id: int,
    attempt_id: int,
    score: int,
    time_taken_seconds: int,
) -> None:
    await db.execute(
        "INSERT INTO leaderboard (exam_id, user_id, attempt_id, score, time_taken_seconds) VALUES (?, ?, ?, ?, ?)",
        (exam_id, user_id, attempt_id, score, time_taken_seconds),
    )
    await db.commit()


async def recompute_ranks(db, exam_id: int) -> None:
    await db.execute(
        """
        UPDATE leaderboard
        SET rank = (
            SELECT rank FROM (
                SELECT id, RANK() OVER (PARTITION BY exam_id ORDER BY score DESC, time_taken_seconds ASC) AS rank
                FROM leaderboard
                WHERE exam_id = ?
            ) ranked
            WHERE ranked.id = leaderboard.id
        )
        WHERE exam_id = ?
        """,
        (exam_id, exam_id),
    )
    await db.commit()


async def get_exam_leaderboard(db, exam_id: int) -> List[Dict[str, Any]]:
    return await leaderboard_model.get_exam_leaderboard(db, exam_id)


async def get_global_leaderboard(db) -> List[Dict[str, Any]]:
    return await leaderboard_model.get_global_leaderboard(db)
