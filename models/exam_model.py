from typing import Any, Dict, List, Optional
import json


def _row_to_exam(row) -> Optional[dict]:
    if row is None:
        return None

    if len(row) > 13:
        # full query with approval status
        requires_approval = bool(row[10])
        approval_status = row[13] if row[13] is not None else ("pending" if requires_approval else "approved")
        created_at = row[11]
        updated_at = row[12]
    elif len(row) == 13:
        # query with requires_approval but no status column
        requires_approval = bool(row[10])
        approval_status = "pending" if requires_approval else "approved"
        created_at = row[11]
        updated_at = row[12]
    elif len(row) == 12:
        # legacy query without approval columns
        requires_approval = False
        approval_status = "approved"
        created_at = row[10]
        updated_at = row[11]
    else:
        # older legacy query shape
        requires_approval = False
        approval_status = "approved"
        created_at = row[8] if len(row) > 8 else None
        updated_at = row[9] if len(row) > 9 else None

    return {
        "id": row[0],
        "user_id": row[1],
        "title": row[2],
        "description": row[3],
        "duration_minutes": row[4],
        "total_marks": row[5],
        "is_public": bool(row[6]),
        "randomize_order": bool(row[7]),
        "randomize_options": bool(row[8]) if len(row) > 8 else False,
        "secure_mode": bool(row[9]) if len(row) > 9 else False,
        "requires_approval": requires_approval,
        "approval_status": approval_status,
        "created_at": created_at,
        "updated_at": updated_at,
    }


async def _get_exam_questions(db, exam_id: int) -> List[dict]:
    cursor = await db.execute(
        """
        SELECT eq.question_id, q.title, q.type, q.difficulty, eq.marks, eq.question_order
        FROM exam_questions eq
        JOIN questions q ON q.id = eq.question_id
        WHERE eq.exam_id = ?
        ORDER BY eq.question_order
        """,
        (exam_id,),
    )
    rows = await cursor.fetchall()
    return [
        {
            "question_id": row[0],
            "title": row[1],
            "type": row[2],
            "difficulty": row[3],
            "marks": row[4],
            "question_order": row[5],
        }
        for row in rows
    ]


async def create_exam(
    db,
    user_id: int,
    title: str,
    description: str | None,
    duration_minutes: int,
    total_marks: int,
    is_public: bool,
    randomize_order: bool,
    randomize_options: bool,
    secure_mode: bool,
    questions: list[dict[str, Any]],
    requires_approval: bool = False,
) -> dict:
    # Try to insert the new column; fall back to legacy INSERT if missing.
    try:
        cursor = await db.execute(
            "INSERT INTO exams (user_id, title, description, duration_minutes, total_marks, is_public, randomize_order, randomize_options, secure_mode, requires_approval) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                user_id,
                title,
                description,
                duration_minutes,
                total_marks,
                int(is_public),
                int(randomize_order),
                int(randomize_options),
                int(secure_mode),
                int(requires_approval),
            ),
        )
    except Exception:
        cursor = await db.execute(
            "INSERT INTO exams (user_id, title, description, duration_minutes, total_marks, is_public, randomize_order, randomize_options, secure_mode) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                user_id,
                title,
                description,
                duration_minutes,
                total_marks,
                int(is_public),
                int(randomize_order),
                int(randomize_options),
                int(secure_mode),
            ),
        )
    exam_id = cursor.lastrowid
    await db.commit()

    if requires_approval:
        try:
            await db.execute(
                "INSERT INTO pending_approvals (content_type, content_id, submitted_by) VALUES ('exam', ?, ?)",
                (exam_id, user_id),
            )
        except Exception:
            pass

    for index, question in enumerate(questions, start=1):
        order = question.get("question_order") or index
        await db.execute(
            "INSERT INTO exam_questions (exam_id, question_id, marks, question_order) VALUES (?, ?, ?, ?)",
            (exam_id, question["question_id"], question.get("marks", 1), order),
        )
    await db.commit()
    return await get_exam_by_id(db, exam_id)


async def get_exam_by_id(db, exam_id: int, current_user_id: int | None = None) -> Optional[dict]:
    current_user_id = current_user_id if current_user_id is not None else -1
    # Prefer SELECT that includes approval info; fall back to legacy SELECT
    try:
        cursor = await db.execute(
            """
            SELECT id, user_id, title, description, duration_minutes, total_marks, is_public, randomize_order,
                   randomize_options, secure_mode, requires_approval, created_at, updated_at,
                   pa.status
            FROM exams
            LEFT JOIN pending_approvals pa ON pa.content_type = 'exam' AND pa.content_id = exams.id
            WHERE id = ?
            """,
            (exam_id,),
        )
        row = await cursor.fetchone()
        exam = _row_to_exam(row)
        if exam is None:
            return None
        if exam["requires_approval"] and exam["user_id"] != current_user_id:
            return None
    except Exception:
        cursor = await db.execute(
            "SELECT id, user_id, title, description, duration_minutes, total_marks, is_public, randomize_order, randomize_options, secure_mode, created_at, updated_at FROM exams WHERE id = ?",
            (exam_id,),
        )
        row = await cursor.fetchone()
        exam = _row_to_exam(row)
        if exam is None:
            return None
        exam["requires_approval"] = False
    exam["questions"] = await _get_exam_questions(db, exam_id)
    return exam


async def list_exams(db, page: int = 1, limit: int = 20, only_public: bool = True) -> list[dict]:
    offset = (page - 1) * limit
    try:
        query = """
            SELECT id, user_id, title, description, duration_minutes, total_marks, is_public, randomize_order,
                   randomize_options, secure_mode, requires_approval, created_at, updated_at,
                   pa.status
            FROM exams
            LEFT JOIN pending_approvals pa ON pa.content_type = 'exam' AND pa.content_id = exams.id
        """
        params: list = []
        if only_public:
            query += " WHERE is_public = 1 AND requires_approval = 0"
        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        cursor = await db.execute(query, tuple(params))
        rows = await cursor.fetchall()
        exams = [_row_to_exam(row) for row in rows]
    except Exception:
        query = "SELECT id, user_id, title, description, duration_minutes, total_marks, is_public, randomize_order, randomize_options, secure_mode, created_at, updated_at FROM exams"
        params: list = []
        if only_public:
            query += " WHERE is_public = 1"
        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        cursor = await db.execute(query, tuple(params))
        rows = await cursor.fetchall()
        exams = [_row_to_exam(row) for row in rows]
    for exam in exams:
        exam["questions"] = await _get_exam_questions(db, exam["id"])
    return exams


async def update_exam(
    db,
    exam_id: int,
    title: str | None = None,
    description: str | None = None,
    duration_minutes: int | None = None,
    total_marks: int | None = None,
    is_public: bool | None = None,
    randomize_order: bool | None = None,
    randomize_options: bool | None = None,
    secure_mode: bool | None = None,
    questions: list[dict[str, Any]] | None = None,
) -> Optional[dict]:
    current = await get_exam_by_id(db, exam_id)
    if current is None:
        return None
    fields: list[str] = []
    values: list[Any] = []
    if title is not None:
        fields.append("title = ?")
        values.append(title)
    if description is not None:
        fields.append("description = ?")
        values.append(description)
    if duration_minutes is not None:
        fields.append("duration_minutes = ?")
        values.append(duration_minutes)
    if total_marks is not None:
        fields.append("total_marks = ?")
        values.append(total_marks)
    if is_public is not None:
        fields.append("is_public = ?")
        values.append(int(is_public))
    if randomize_order is not None:
        fields.append("randomize_order = ?")
        values.append(int(randomize_order))
    if randomize_options is not None:
        fields.append("randomize_options = ?")
        values.append(int(randomize_options))
    if secure_mode is not None:
        fields.append("secure_mode = ?")
        values.append(int(secure_mode))
    if fields:
        values.append(exam_id)
        await db.execute(f"UPDATE exams SET {', '.join(fields)}, updated_at = datetime('now') WHERE id = ?", tuple(values))

    if questions is not None:
        await db.execute("DELETE FROM exam_questions WHERE exam_id = ?", (exam_id,))
        for index, question in enumerate(questions, start=1):
            order = question.get("question_order") or index
            await db.execute(
                "INSERT INTO exam_questions (exam_id, question_id, marks, question_order) VALUES (?, ?, ?, ?)",
                (exam_id, question["question_id"], question.get("marks", 1), order),
            )

    await db.commit()
    return await get_exam_by_id(db, exam_id)


async def delete_exam(db, exam_id: int) -> None:
    await db.execute("DELETE FROM exams WHERE id = ?", (exam_id,))
    await db.execute("DELETE FROM pending_approvals WHERE content_type = 'exam' AND content_id = ?", (exam_id,))
    await db.commit()


async def _get_attempt_row(db, attempt_id: int) -> Optional[dict]:
    cursor = await db.execute(
        "SELECT id, exam_id, user_id, attempt_number, score, total_marks, time_taken_seconds, status, started_at, last_saved_at, question_order, submitted_at, answers FROM exam_attempts WHERE id = ?",
        (attempt_id,),
    )
    row = await cursor.fetchone()
    if row is None:
        return None
    return {
        "id": row[0],
        "exam_id": row[1],
        "user_id": row[2],
        "attempt_number": row[3],
        "score": row[4],
        "total_marks": row[5],
        "time_taken_seconds": row[6],
        "status": row[7],
        "started_at": row[8],
        "last_saved_at": row[9],
        "question_order": json.loads(row[10] or "[]"),
        "submitted_at": row[11],
        "answers": json.loads(row[12] or "{}"),
    }


async def create_attempt(db, exam_id: int, user_id: int, question_order: list[dict[str, Any]] | None = None) -> Optional[dict]:
    cursor = await db.execute(
        "SELECT COUNT(*) FROM exam_attempts WHERE exam_id = ? AND user_id = ?",
        (exam_id, user_id),
    )
    row = await cursor.fetchone()
    attempt_number = (row[0] if row else 0) + 1

    cursor = await db.execute(
        "SELECT SUM(marks) FROM exam_questions WHERE exam_id = ?",
        (exam_id,),
    )
    total_marks_row = await cursor.fetchone()
    total_marks = total_marks_row[0] if total_marks_row and total_marks_row[0] is not None else 0

    if question_order is None:
        cursor = await db.execute(
            "SELECT question_id, marks, question_order FROM exam_questions WHERE exam_id = ? ORDER BY question_order",
            (exam_id,),
        )
        rows = await cursor.fetchall()
        question_order = [
            {"question_id": row[0], "marks": row[1], "question_order": row[2]}
            for row in rows
        ]

    cursor = await db.execute(
        "INSERT INTO exam_attempts (exam_id, user_id, attempt_number, total_marks, status, started_at, last_saved_at, question_order, answers) VALUES (?, ?, ?, ?, ?, datetime('now'), datetime('now'), ?, ?)",
        (exam_id, user_id, attempt_number, total_marks, 'in_progress', json.dumps(question_order), json.dumps({})),
    )
    await db.commit()
    return await get_attempt(db, cursor.lastrowid)


async def get_latest_active_attempt(db, exam_id: int, user_id: int) -> Optional[dict]:
    cursor = await db.execute(
        "SELECT id FROM exam_attempts WHERE exam_id = ? AND user_id = ? AND status = 'in_progress' ORDER BY started_at DESC LIMIT 1",
        (exam_id, user_id),
    )
    row = await cursor.fetchone()
    if row is None:
        return None
    return await get_attempt(db, row[0])


async def save_attempt_progress(db, attempt_id: int, user_id: int, answers: dict[str, Any], time_taken_seconds: int) -> Optional[dict]:
    attempt = await get_attempt(db, attempt_id)
    if attempt is None or attempt["user_id"] != user_id or attempt["status"] != "in_progress":
        return None
    await db.execute(
        "UPDATE exam_attempts SET answers = ?, time_taken_seconds = ?, last_saved_at = datetime('now') WHERE id = ?",
        (json.dumps(answers), time_taken_seconds, attempt_id),
    )
    await db.commit()
    return await get_attempt(db, attempt_id)


async def get_attempt(db, attempt_id: int) -> Optional[dict]:
    return await _get_attempt_row(db, attempt_id)


async def submit_attempt(db, attempt_id: int, user_id: int, score: int, time_taken_seconds: int, answers: dict[str, Any]) -> Optional[dict]:
    attempt = await get_attempt(db, attempt_id)
    if attempt is None or attempt["user_id"] != user_id:
        return None
    await db.execute(
        "UPDATE exam_attempts SET score = ?, time_taken_seconds = ?, answers = ?, status = 'submitted', last_saved_at = datetime('now'), submitted_at = datetime('now') WHERE id = ?",
        (score, time_taken_seconds, json.dumps(answers), attempt_id),
    )
    await db.commit()
    return await get_attempt(db, attempt_id)
