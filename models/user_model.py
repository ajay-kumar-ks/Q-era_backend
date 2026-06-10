from collections import defaultdict
from datetime import date, datetime, timedelta
import json
from typing import Optional


def row_to_user(row) -> Optional[dict]:
    if row is None:
        return None
    return {
        "id": row[0],
        "name": row[1],
        "email": row[2],
        "password_hash": row[3],
        "role": row[4],
        "is_suspended": bool(row[5]),
        "avatar_url": row[6],
        "bio": row[7],
        "preferred_topics": _parse_json_list(row[8]) if len(row) > 10 else [],
        "learning_goals": row[9] if len(row) > 10 else None,
        "notification_preferences": _parse_json_object(row[10]) if len(row) > 10 else {},
        "created_at": row[11] if len(row) > 10 else row[8],
        "updated_at": row[12] if len(row) > 10 else row[9],
    }


async def create_user(db, name: str, email: str, password_hash: str, role: str = "student", avatar_url: Optional[str] = None, bio: Optional[str] = None) -> dict:
    cursor = await db.execute(
        """
        INSERT INTO users (name, email, password_hash, role, avatar_url, bio)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (name, email, password_hash, role, avatar_url, bio),
    )
    await db.commit()
    user_id = cursor.lastrowid
    return await get_user_by_id(db, user_id)


async def get_user_by_email(db, email: str) -> Optional[dict]:
    cursor = await db.execute(
        "SELECT id, name, email, password_hash, role, is_suspended, avatar_url, bio, preferred_topics, learning_goals, notification_preferences, created_at, updated_at FROM users WHERE email = ?",
        (email,),
    )
    row = await cursor.fetchone()
    return row_to_user(row)


async def get_user_by_id(db, user_id: int) -> Optional[dict]:
    cursor = await db.execute(
        "SELECT id, name, email, password_hash, role, is_suspended, avatar_url, bio, preferred_topics, learning_goals, notification_preferences, created_at, updated_at FROM users WHERE id = ?",
        (user_id,),
    )
    row = await cursor.fetchone()
    return row_to_user(row)


async def update_user(
    db,
    user_id: int,
    name: str | None = None,
    avatar_url: str | None = None,
    bio: str | None = None,
    preferred_topics: list[str] | None = None,
    learning_goals: str | None = None,
    notification_preferences: dict | None = None,
    is_suspended: bool | None = None,
) -> Optional[dict]:
    current = await get_user_by_id(db, user_id)
    if current is None:
        return None
    fields: list[str] = []
    values: list = []
    if name is not None:
        fields.append("name = ?")
        values.append(name)
    if avatar_url is not None:
        fields.append("avatar_url = ?")
        values.append(avatar_url)
    if bio is not None:
        fields.append("bio = ?")
        values.append(bio)
    if preferred_topics is not None:
        fields.append("preferred_topics = ?")
        values.append(json.dumps(preferred_topics))
    if learning_goals is not None:
        fields.append("learning_goals = ?")
        values.append(learning_goals)
    if notification_preferences is not None:
        fields.append("notification_preferences = ?")
        values.append(json.dumps(notification_preferences))
    if is_suspended is not None:
        fields.append("is_suspended = ?")
        values.append(int(is_suspended))
    if fields:
        values.append(user_id)
        await db.execute(f"UPDATE users SET {', '.join(fields)}, updated_at = datetime('now') WHERE id = ?", tuple(values))
        await db.commit()
    return await get_user_by_id(db, user_id)


async def get_user_profile(db, user_id: int) -> Optional[dict]:
    user = await get_user_by_id(db, user_id)
    if user is None:
        return None

    cursor = await db.execute("SELECT COUNT(*) FROM questions WHERE user_id = ?", (user_id,))
    questions_created = (await cursor.fetchone())[0]

    cursor = await db.execute("SELECT COUNT(*) FROM exams WHERE user_id = ?", (user_id,))
    exams_created = (await cursor.fetchone())[0]

    cursor = await db.execute("SELECT COUNT(DISTINCT exam_id) FROM exam_attempts WHERE user_id = ?", (user_id,))
    exams_attended = (await cursor.fetchone())[0]

    cursor = await db.execute(
        "SELECT AVG(CAST(score AS FLOAT) / NULLIF(total_marks, 0) * 100) FROM exam_attempts WHERE user_id = ? AND total_marks > 0",
        (user_id,),
    )
    accuracy_row = await cursor.fetchone()
    accuracy = float(accuracy_row[0]) if accuracy_row and accuracy_row[0] is not None else 0.0

    cursor = await db.execute(
        """
        SELECT rank FROM (
            SELECT l.user_id AS user_id, RANK() OVER (ORDER BY SUM(l.score) DESC, AVG(CAST(l.score AS FLOAT) / NULLIF(ea.total_marks, 0) * 100) DESC) AS rank
            FROM leaderboard l
            JOIN exam_attempts ea ON ea.id = l.attempt_id
            GROUP BY l.user_id
        ) ranked
        WHERE ranked.user_id = ?
        """,
        (user_id,),
    )
    rank_row = await cursor.fetchone()
    global_rank = int(rank_row[0]) if rank_row and rank_row[0] is not None else None

    # Try to include approval status; fall back if schema isn't migrated.
    try:
        cursor = await db.execute(
            """
            SELECT q.id, q.title, q.difficulty, q.created_at,
                   CASE WHEN q.requires_approval = 0 THEN 'approved' ELSE COALESCE(pa.status, 'pending') END AS status
            FROM questions q
            LEFT JOIN pending_approvals pa ON pa.content_type = 'question' AND pa.content_id = q.id
            WHERE q.user_id = ?
            ORDER BY q.created_at DESC
            LIMIT 5
            """,
            (user_id,),
        )
        recent_questions = [
            {"id": row[0], "title": row[1], "difficulty": row[2], "created_at": row[3], "status": row[4]}
            for row in await cursor.fetchall()
        ]
    except Exception:
        cursor = await db.execute(
            "SELECT id, title, difficulty, created_at FROM questions WHERE user_id = ? ORDER BY created_at DESC LIMIT 5",
            (user_id,),
        )
        recent_questions = [
            {"id": row[0], "title": row[1], "difficulty": row[2], "created_at": row[3], "status": "approved"}
            for row in await cursor.fetchall()
        ]

    try:
        cursor = await db.execute(
            """
            SELECT e.id, e.title, e.duration_minutes, e.total_marks, e.created_at,
                   CASE WHEN e.requires_approval = 0 THEN 'approved' ELSE COALESCE(pa.status, 'pending') END AS status
            FROM exams e
            LEFT JOIN pending_approvals pa ON pa.content_type = 'exam' AND pa.content_id = e.id
            WHERE e.user_id = ?
            ORDER BY e.created_at DESC
            LIMIT 5
            """,
            (user_id,),
        )
        recent_exams = [
            {"id": row[0], "title": row[1], "duration_minutes": row[2], "total_marks": row[3], "created_at": row[4], "status": row[5]}
            for row in await cursor.fetchall()
        ]
    except Exception:
        cursor = await db.execute(
            "SELECT id, title, duration_minutes, total_marks, created_at FROM exams WHERE user_id = ? ORDER BY created_at DESC LIMIT 5",
            (user_id,),
        )
        recent_exams = [
            {"id": row[0], "title": row[1], "duration_minutes": row[2], "total_marks": row[3], "created_at": row[4], "status": "approved"}
            for row in await cursor.fetchall()
        ]

    profile = {
        "id": user["id"],
        "name": user["name"],
        "email": user["email"],
        "role": user["role"],
        "avatar_url": user["avatar_url"],
        "bio": user["bio"],
        "preferred_topics": user["preferred_topics"],
        "learning_goals": user["learning_goals"],
        "notification_preferences": user["notification_preferences"],
        "created_at": user["created_at"],
        "updated_at": user["updated_at"],
        "stats": {
            "global_rank": global_rank,
            "exams_attended": exams_attended,
            "exams_created": exams_created,
            "questions_created": questions_created,
            "accuracy": accuracy,
        },
        "recent_questions": recent_questions,
        "recent_exams": recent_exams,
    }
    return profile


async def get_user_bookmarks(db, user_id: int) -> list[dict]:
    cursor = await db.execute(
        """
        SELECT q.id, q.title, q.description, q.type, q.difficulty, q.likes_count, q.created_at
        FROM bookmarks b
        JOIN questions q ON q.id = b.question_id
        WHERE b.user_id = ?
        ORDER BY b.created_at DESC
        """,
        (user_id,),
    )
    rows = await cursor.fetchall()
    return [
        {
            "id": row[0],
            "title": row[1],
            "description": row[2],
            "type": row[3],
            "difficulty": row[4],
            "likes_count": row[5],
            "created_at": row[6],
        }
        for row in rows
    ]


async def get_user_questions(db, user_id: int, page: int = 1, limit: int = 10) -> dict:
    offset = (page - 1) * limit
    # Total count
    count_cursor = await db.execute(
        "SELECT COUNT(*) FROM questions WHERE user_id = ?", (user_id,)
    )
    count_row = await count_cursor.fetchone()
    total = count_row[0] if count_row else 0

    cursor = await db.execute(
        """
        SELECT q.id, q.title, q.description, q.type, q.difficulty, q.is_public, q.created_at,
               CASE WHEN q.requires_approval = 0 THEN 'approved' ELSE COALESCE(pa.status, 'pending') END AS status
        FROM questions q
        LEFT JOIN pending_approvals pa ON pa.content_type = 'question' AND pa.content_id = q.id
        WHERE q.user_id = ?
        ORDER BY q.created_at DESC
        LIMIT ? OFFSET ?
        """,
        (user_id, limit, offset),
    )
    rows = await cursor.fetchall()
    items = [
        {
            "id": row[0],
            "title": row[1],
            "description": row[2],
            "type": row[3],
            "difficulty": row[4],
            "is_public": bool(row[5]),
            "created_at": str(row[6]),
            "status": row[7],
        }
        for row in rows
    ]
    return {"items": items, "total": total, "page": page, "limit": limit}


async def get_user_exams(db, user_id: int, page: int = 1, limit: int = 10) -> dict:
    offset = (page - 1) * limit
    count_cursor = await db.execute(
        "SELECT COUNT(*) FROM exams WHERE user_id = ?", (user_id,)
    )
    count_row = await count_cursor.fetchone()
    total = count_row[0] if count_row else 0

    cursor = await db.execute(
        """
        SELECT e.id, e.title, e.description, e.duration_minutes, e.total_marks, e.is_public, e.created_at,
               CASE WHEN e.requires_approval = 0 THEN 'approved' ELSE COALESCE(pa.status, 'pending') END AS status
        FROM exams e
        LEFT JOIN pending_approvals pa ON pa.content_type = 'exam' AND pa.content_id = e.id
        WHERE e.user_id = ?
        ORDER BY e.created_at DESC
        LIMIT ? OFFSET ?
        """,
        (user_id, limit, offset),
    )
    rows = await cursor.fetchall()
    items = [
        {
            "id": row[0],
            "title": row[1],
            "description": row[2],
            "duration_minutes": row[3],
            "total_marks": row[4],
            "is_public": bool(row[5]),
            "created_at": str(row[6]),
            "status": row[7],
        }
        for row in rows
    ]
    return {"items": items, "total": total, "page": page, "limit": limit}


def _parse_json_object(value: str | None) -> dict:
    try:
        parsed = json.loads(value or "{}")
        return parsed if isinstance(parsed, dict) else {}
    except (TypeError, json.JSONDecodeError):
        return {}


def _parse_json_list(value: str | None) -> list:
    try:
        parsed = json.loads(value or "[]")
        return parsed if isinstance(parsed, list) else []
    except (TypeError, json.JSONDecodeError):
        return []


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        try:
            return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return None


def _percent(score: int | float | None, total: int | float | None) -> float:
    if not total:
        return 0.0
    return round((float(score or 0) / float(total)) * 100, 1)


async def _get_question_meta(db, question_ids: set[int]) -> dict[int, dict]:
    if not question_ids:
        return {}
    placeholders = ",".join("?" for _ in question_ids)
    cursor = await db.execute(
        f"""
        SELECT q.id, q.title, q.type, q.difficulty, q.correct_answer,
               COALESCE(GROUP_CONCAT(t.name), '') AS tags
        FROM questions q
        LEFT JOIN question_tags qt ON qt.question_id = q.id
        LEFT JOIN tags t ON t.id = qt.tag_id
        WHERE q.id IN ({placeholders})
        GROUP BY q.id
        """,
        tuple(question_ids),
    )
    rows = await cursor.fetchall()
    return {
        row[0]: {
            "id": row[0],
            "title": row[1],
            "type": row[2],
            "difficulty": row[3],
            "correct_answer": row[4] or "",
            "tags": [tag for tag in (row[5] or "").split(",") if tag],
        }
        for row in rows
    }


async def get_learning_progress(db, user_id: int) -> dict:
    cursor = await db.execute(
        """
        SELECT ea.id, ea.exam_id, e.title, ea.attempt_number, ea.score, ea.total_marks,
               ea.time_taken_seconds, ea.submitted_at, ea.answers, ea.status
        FROM exam_attempts ea
        JOIN exams e ON e.id = ea.exam_id
        WHERE ea.user_id = ? AND ea.status = 'submitted'
        ORDER BY ea.submitted_at DESC, ea.id DESC
        """,
        (user_id,),
    )
    attempt_rows = await cursor.fetchall()

    attempts = []
    answered_question_ids: set[int] = set()
    for row in attempt_rows:
        answers = _parse_json_object(row[8])
        answered_question_ids.update(int(qid) for qid in answers.keys() if str(qid).isdigit())
        attempts.append(
            {
                "id": row[0],
                "exam_id": row[1],
                "exam_title": row[2],
                "attempt_number": row[3],
                "score": row[4],
                "total_marks": row[5],
                "time_taken_seconds": row[6],
                "submitted_at": row[7],
                "answers": answers,
                "status": row[9],
                "percentage": _percent(row[4], row[5]),
            }
        )

    question_meta = await _get_question_meta(db, answered_question_ids)
    difficulty_totals = defaultdict(lambda: {"correct": 0, "total": 0})
    tag_totals = defaultdict(lambda: {"correct": 0, "total": 0})
    mistake_by_question: dict[int, dict] = {}

    for attempt in attempts:
        submitted_at = attempt["submitted_at"]
        for raw_qid, answer in attempt["answers"].items():
            if not str(raw_qid).isdigit():
                continue
            question_id = int(raw_qid)
            question = question_meta.get(question_id)
            if not question:
                continue
            given = str(answer or "").strip()
            expected = str(question["correct_answer"] or "").strip()
            correct = bool(given) and given.lower() == expected.lower()
            difficulty = question["difficulty"] or "unknown"
            difficulty_totals[difficulty]["total"] += 1
            difficulty_totals[difficulty]["correct"] += int(correct)
            tags = question["tags"] or ["untagged"]
            for tag in tags:
                tag_totals[tag]["total"] += 1
                tag_totals[tag]["correct"] += int(correct)
            if not correct and question_id not in mistake_by_question:
                mistake_by_question[question_id] = {
                    "question_id": question_id,
                    "title": question["title"],
                    "difficulty": difficulty,
                    "type": question["type"],
                    "tags": question["tags"],
                    "your_answer": given,
                    "correct_answer": expected,
                    "exam_id": attempt["exam_id"],
                    "exam_title": attempt["exam_title"],
                    "submitted_at": submitted_at,
                }

    recent_results = [
        {
            "attempt_id": attempt["id"],
            "exam_id": attempt["exam_id"],
            "exam_title": attempt["exam_title"],
            "score": attempt["score"],
            "total_marks": attempt["total_marks"],
            "percentage": attempt["percentage"],
            "submitted_at": attempt["submitted_at"],
        }
        for attempt in attempts[:8]
    ]

    score_history = list(reversed(recent_results))
    accuracy_by_difficulty = [
        {
            "difficulty": difficulty,
            "correct": values["correct"],
            "total": values["total"],
            "accuracy": _percent(values["correct"], values["total"]),
        }
        for difficulty, values in sorted(difficulty_totals.items())
    ]

    trend_by_day = defaultdict(int)
    submitted_days: set[date] = set()
    for attempt in attempts:
        submitted = _parse_datetime(attempt["submitted_at"])
        if submitted:
            day = submitted.date()
            trend_by_day[day.isoformat()] += 1
            submitted_days.add(day)

    today = date.today()
    completion_trend = [
        {"date": (today - timedelta(days=offset)).isoformat(), "completed": trend_by_day[(today - timedelta(days=offset)).isoformat()]}
        for offset in range(13, -1, -1)
    ]

    streak = 0
    cursor_day = max(submitted_days) if submitted_days else today
    while cursor_day in submitted_days:
        streak += 1
        cursor_day -= timedelta(days=1)

    weak_topics = [
        {
            "tag": tag,
            "correct": values["correct"],
            "total": values["total"],
            "accuracy": _percent(values["correct"], values["total"]),
        }
        for tag, values in tag_totals.items()
        if values["total"] > values["correct"]
    ]
    weak_topics.sort(key=lambda item: (item["accuracy"], -item["total"], item["tag"]))

    review_mistakes = sorted(
        mistake_by_question.values(),
        key=lambda item: item["submitted_at"] or "",
        reverse=True,
    )[:12]

    cursor = await db.execute(
        """
        SELECT q.id, q.title, q.description, q.type, q.difficulty,
               COALESCE(GROUP_CONCAT(t.name), '') AS tags
        FROM bookmarks b
        JOIN questions q ON q.id = b.question_id
        LEFT JOIN question_tags qt ON qt.question_id = q.id
        LEFT JOIN tags t ON t.id = qt.tag_id
        WHERE b.user_id = ?
        GROUP BY q.id, b.created_at
        ORDER BY b.created_at DESC
        LIMIT 6
        """,
        (user_id,),
    )
    bookmarked_questions = [
        {
            "id": row[0],
            "title": row[1],
            "description": row[2],
            "type": row[3],
            "difficulty": row[4],
            "tags": [tag for tag in (row[5] or "").split(",") if tag],
        }
        for row in await cursor.fetchall()
    ]

    recommendation_tags = [topic["tag"] for topic in weak_topics[:4] if topic["tag"] != "untagged"]
    for question in bookmarked_questions:
        for tag in question["tags"]:
            if tag not in recommendation_tags:
                recommendation_tags.append(tag)

    recommended_questions = []
    if recommendation_tags:
        placeholders = ",".join("?" for _ in recommendation_tags)
        excluded = answered_question_ids | {question["id"] for question in bookmarked_questions}
        excluded_clause = ""
        params: list = [*recommendation_tags]
        if excluded:
            excluded_placeholders = ",".join("?" for _ in excluded)
            excluded_clause = f"AND q.id NOT IN ({excluded_placeholders})"
            params.extend(excluded)
        cursor = await db.execute(
            f"""
            SELECT q.id, q.title, q.description, q.type, q.difficulty,
                   COALESCE(GROUP_CONCAT(DISTINCT t.name), '') AS tags
            FROM questions q
            JOIN question_tags qt ON qt.question_id = q.id
            JOIN tags t ON t.id = qt.tag_id
            WHERE q.is_public = 1
              AND q.is_flagged = 0
              AND t.name IN ({placeholders})
              {excluded_clause}
            GROUP BY q.id
            ORDER BY q.likes_count DESC, q.created_at DESC
            LIMIT 6
            """,
            tuple(params),
        )
        recommended_questions = [
            {
                "id": row[0],
                "title": row[1],
                "description": row[2],
                "type": row[3],
                "difficulty": row[4],
                "tags": [tag for tag in (row[5] or "").split(",") if tag],
            }
            for row in await cursor.fetchall()
        ]

    weak_exam_ids = [attempt["exam_id"] for attempt in attempts if attempt["percentage"] < 70][:4]
    practice_again = []
    if weak_exam_ids:
        placeholders = ",".join("?" for _ in weak_exam_ids)
        cursor = await db.execute(
            f"""
            SELECT id, title, duration_minutes, total_marks
            FROM exams
            WHERE id IN ({placeholders})
            ORDER BY created_at DESC
            """,
            tuple(weak_exam_ids),
        )
        practice_again = [
            {"id": row[0], "title": row[1], "duration_minutes": row[2], "total_marks": row[3]}
            for row in await cursor.fetchall()
        ]

    recommended_exams = []
    if recommendation_tags:
        placeholders = ",".join("?" for _ in recommendation_tags)
        attempted_exam_ids = {attempt["exam_id"] for attempt in attempts}
        excluded_clause = ""
        params = [*recommendation_tags]
        if attempted_exam_ids:
            excluded_placeholders = ",".join("?" for _ in attempted_exam_ids)
            excluded_clause = f"AND e.id NOT IN ({excluded_placeholders})"
            params.extend(attempted_exam_ids)
        cursor = await db.execute(
            f"""
            SELECT e.id, e.title, e.duration_minutes, e.total_marks,
                   COALESCE(GROUP_CONCAT(DISTINCT t.name), '') AS matched_tags
            FROM exams e
            JOIN exam_questions eq ON eq.exam_id = e.id
            JOIN question_tags qt ON qt.question_id = eq.question_id
            JOIN tags t ON t.id = qt.tag_id
            WHERE e.is_public = 1
              AND t.name IN ({placeholders})
              {excluded_clause}
            GROUP BY e.id
            ORDER BY e.created_at DESC
            LIMIT 6
            """,
            tuple(params),
        )
        recommended_exams = [
            {
                "id": row[0],
                "title": row[1],
                "duration_minutes": row[2],
                "total_marks": row[3],
                "tags": [tag for tag in (row[4] or "").split(",") if tag],
            }
            for row in await cursor.fetchall()
        ]

    return {
        "summary": {
            "total_exams": len({attempt["exam_id"] for attempt in attempts}),
            "submitted_attempts": len(attempts),
            "average_score": _percent(sum(attempt["score"] for attempt in attempts), sum(attempt["total_marks"] for attempt in attempts)),
            "streak_days": streak,
            "review_due": len(review_mistakes),
        },
        "score_history": score_history,
        "accuracy_by_difficulty": accuracy_by_difficulty,
        "completion_trend": completion_trend,
        "recent_results": recent_results,
        "weak_topics": weak_topics[:8],
        "review_mistakes": review_mistakes,
        "recommendations": {
            "practice_again": practice_again,
            "bookmarked_questions": bookmarked_questions,
            "recommended_questions": recommended_questions,
            "recommended_exams": recommended_exams,
        },
    }
