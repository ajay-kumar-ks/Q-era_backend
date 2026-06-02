from typing import Any, Dict, List


async def get_exam_leaderboard(db, exam_id: int) -> List[Dict[str, Any]]:
    cursor = await db.execute(
        """
        SELECT l.id, l.user_id, u.name, u.email, l.score, l.time_taken_seconds, l.rank
        FROM leaderboard l
        JOIN users u ON u.id = l.user_id
        WHERE l.exam_id = ?
        ORDER BY l.rank ASC, l.score DESC, l.time_taken_seconds ASC
        """,
        (exam_id,),
    )
    rows = await cursor.fetchall()
    return [
        {
            "id": row[0],
            "user_id": row[1],
            "name": row[2],
            "email": row[3],
            "score": row[4],
            "time_taken_seconds": row[5],
            "rank": row[6],
        }
        for row in rows
    ]


async def get_global_leaderboard(db) -> List[Dict[str, Any]]:
    cursor = await db.execute(
        """
        SELECT u.id, u.name, u.email, SUM(l.score) AS total_score, COUNT(DISTINCT l.exam_id) AS exams_attended,
               AVG(CAST(l.score AS FLOAT) / NULLIF(ea.total_marks, 0) * 100) AS accuracy
        FROM leaderboard l
        JOIN users u ON u.id = l.user_id
        JOIN exam_attempts ea ON ea.id = l.attempt_id
        GROUP BY u.id
        ORDER BY total_score DESC, accuracy DESC
        """,
    )
    rows = await cursor.fetchall()
    return [
        {
            "user_id": row[0],
            "name": row[1],
            "email": row[2],
            "total_score": int(row[3] or 0),
            "exams_attended": int(row[4] or 0),
            "accuracy": float(row[5] or 0.0),
        }
        for row in rows
    ]
