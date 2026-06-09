from typing import Any, Dict, List, Optional


def _row_to_question(row) -> Optional[dict]:
    if row is None:
        return None
    requires_approval = bool(row[19]) if len(row) > 19 else False
    approval_status = row[20] if len(row) > 20 and row[20] is not None else ("pending" if requires_approval else "approved")
    return {
        "id": row[0],
        "user_id": row[1],
        "title": row[2],
        "description": row[3],
        "type": row[4],
        "correct_answer": row[5],
        "difficulty": row[6],
        "explanation": row[7],
        "is_public": bool(row[8]),
        "is_flagged": bool(row[9]),
        "likes_count": row[10],
        "created_at": row[11],
        "updated_at": row[12],
        "author_name": row[13],
        "liked": bool(row[14]),
        "bookmarked": bool(row[15]) if len(row) > 15 else False,
        "image_url": row[16] if len(row) > 16 else None,
        "media_url": row[17] if len(row) > 17 else None,
        "attachment_url": row[18] if len(row) > 18 else None,
        "requires_approval": requires_approval,
        "approval_status": approval_status,
    }


async def _get_tags(db, question_id: int) -> List[dict]:
    cursor = await db.execute(
        "SELECT t.id, t.name FROM tags t JOIN question_tags qt ON qt.tag_id = t.id WHERE qt.question_id = ?",
        (question_id,),
    )
    rows = await cursor.fetchall()
    return [{"id": row[0], "name": row[1]} for row in rows]


async def _get_options(db, question_id: int) -> List[dict]:
    cursor = await db.execute(
        "SELECT id, option_text, option_order, image_url FROM question_options WHERE question_id = ? ORDER BY option_order",
        (question_id,),
    )
    rows = await cursor.fetchall()
    return [{"id": row[0], "option_text": row[1], "option_order": row[2], "image_url": row[3]} for row in rows]


async def _get_or_create_tag_id(db, name: str) -> int:
    cursor = await db.execute("SELECT id FROM tags WHERE name = ?", (name,))
    row = await cursor.fetchone()
    if row:
        return row[0]
    await db.execute("INSERT INTO tags (name) VALUES (?)", (name,))
    await db.commit()
    # Re-select after insert — works on both SQLite and PostgreSQL
    cursor = await db.execute("SELECT id FROM tags WHERE name = ?", (name,))
    row = await cursor.fetchone()
    return row[0]


async def create_question(
    db,
    user_id: int,
    title: str,
    description: str | None,
    type: str,
    correct_answer: str | None,
    difficulty: str,
    explanation: str | None,
    image_url: str | None,
    media_url: str | None,
    attachment_url: str | None,
    is_public: bool,
    tag_names: list[str],
    options: list[dict[str, Any]],
    requires_approval: bool = False,
) -> dict:
    # Try an INSERT that includes the new column; if the DB hasn't been migrated
    # yet, fall back to the original INSERT without the column to avoid crashing.
    try:
        cursor = await db.execute(
            """
            INSERT INTO questions (
                user_id, title, description, type, correct_answer, difficulty, explanation,
                image_url, media_url, attachment_url, is_public, requires_approval
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                title,
                description,
                type,
                correct_answer,
                difficulty,
                explanation,
                image_url,
                media_url,
                attachment_url,
                int(is_public),
                int(requires_approval),
            ),
        )
    except Exception:
        cursor = await db.execute(
            """
            INSERT INTO questions (
                user_id, title, description, type, correct_answer, difficulty, explanation,
                image_url, media_url, attachment_url, is_public
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                title,
                description,
                type,
                correct_answer,
                difficulty,
                explanation,
                image_url,
                media_url,
                attachment_url,
                int(is_public),
            ),
        )
    question_id = cursor.lastrowid
    await db.commit()

    # On PostgreSQL, lastrowid can be None if LASTVAL() failed (e.g. after
    # ON CONFLICT DO NOTHING). Re-SELECT to get the real ID reliably.
    if not question_id:
        cursor2 = await db.execute(
            "SELECT id FROM questions WHERE user_id = ? AND title = ? ORDER BY created_at DESC LIMIT 1",
            (user_id, title),
        )
        row2 = await cursor2.fetchone()
        if row2 is None:
            raise RuntimeError("Failed to retrieve question ID after INSERT")
        question_id = row2[0]

    # Defensive guard — should never happen but prevents silent null FK violations
    if not question_id:
        raise RuntimeError(f"question_id is None after INSERT for title='{title}'")

    # Try to insert a pending_approvals row if required; ignore failures if
    # the migrations haven't been applied yet.
    if requires_approval:
        try:
            await db.execute(
                "INSERT INTO pending_approvals (content_type, content_id, submitted_by) VALUES ('question', ?, ?)",
                (question_id, user_id),
            )
        except Exception:
            pass

    for tag_name in tag_names:
        tag_id = await _get_or_create_tag_id(db, tag_name.strip())
        await db.execute(
            "INSERT OR IGNORE INTO question_tags (question_id, tag_id) VALUES (?, ?)",
            (question_id, tag_id),
        )

    for option in options:
        await db.execute(
            "INSERT INTO question_options (question_id, option_text, option_order, image_url) VALUES (?, ?, ?, ?)",
            (question_id, option["option_text"], option["option_order"], option.get("image_url")),
        )

    await db.commit()
    return await get_question_by_id(db, question_id)


async def get_question_by_id(db, question_id: int, current_user_id: int | None = None) -> Optional[dict]:
    current_user_id = current_user_id if current_user_id is not None else -1
    # Try the new SELECT that includes approval columns; if it fails (older DB
    # schema), fall back to the legacy SELECT and mark as approved by default.
    try:
        cursor = await db.execute(
            """
            SELECT q.id, q.user_id, q.title, q.description, q.type, q.correct_answer, q.difficulty,
                   q.explanation, q.is_public, q.is_flagged, q.likes_count, q.created_at, q.updated_at,
                   u.name,
                   EXISTS(SELECT 1 FROM question_likes l WHERE l.user_id = ? AND l.question_id = q.id) AS liked,
                   EXISTS(SELECT 1 FROM bookmarks b WHERE b.user_id = ? AND b.question_id = q.id) AS bookmarked,
                   q.image_url, q.media_url, q.attachment_url, q.requires_approval,
                   pa.status
            FROM questions q
            JOIN users u ON u.id = q.user_id
            LEFT JOIN pending_approvals pa ON pa.content_type = 'question' AND pa.content_id = q.id
            WHERE q.id = ?
            """,
            (current_user_id, current_user_id, question_id),
        )
        row = await cursor.fetchone()
        question = _row_to_question(row)
        if question is None:
            return None
        if question["requires_approval"] and question["user_id"] != current_user_id:
            return None
    except Exception:
        cursor = await db.execute(
            """
            SELECT q.id, q.user_id, q.title, q.description, q.type, q.correct_answer, q.difficulty,
                   q.explanation, q.is_public, q.is_flagged, q.likes_count, q.created_at, q.updated_at,
                   u.name,
                   EXISTS(SELECT 1 FROM question_likes l WHERE l.user_id = ? AND l.question_id = q.id) AS liked,
                   EXISTS(SELECT 1 FROM bookmarks b WHERE b.user_id = ? AND b.question_id = q.id) AS bookmarked,
                   q.image_url, q.media_url, q.attachment_url
            FROM questions q
            JOIN users u ON u.id = q.user_id
            WHERE q.id = ?
            """,
            (current_user_id, current_user_id, question_id),
        )
        row = await cursor.fetchone()
        question = _row_to_question(row)
        if question is None:
            return None
        # Legacy DB: treat as approved and allow owners/admins to access.
        question["requires_approval"] = False
    question["tags"] = await _get_tags(db, question_id)
    question["options"] = await _get_options(db, question_id)
    return question


async def list_questions(db, page: int = 1, limit: int = 20, only_public: bool = True, current_user_id: int | None = None) -> list[dict]:
    current_user_id = current_user_id if current_user_id is not None else -1
    offset = (page - 1) * limit
    # Try to SELECT including approval fields; if the DB schema doesn't have
    # those columns/tables yet, fall back to the legacy SELECT.
    try:
        query = """
            SELECT q.id, q.user_id, q.title, q.description, q.type, q.correct_answer, q.difficulty,
                   q.explanation, q.is_public, q.is_flagged, q.likes_count, q.created_at, q.updated_at,
                   u.name,
                   EXISTS(SELECT 1 FROM question_likes l WHERE l.user_id = ? AND l.question_id = q.id) AS liked,
                   EXISTS(SELECT 1 FROM bookmarks b WHERE b.user_id = ? AND b.question_id = q.id) AS bookmarked,
                   q.image_url, q.media_url, q.attachment_url, q.requires_approval,
                   pa.status
            FROM questions q
            JOIN users u ON u.id = q.user_id
            LEFT JOIN pending_approvals pa ON pa.content_type = 'question' AND pa.content_id = q.id
        """
        params: list = [current_user_id, current_user_id]
        if only_public:
            query += " WHERE q.is_public = 1 AND q.is_flagged = 0 AND q.requires_approval = 0"
        query += " ORDER BY q.created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        cursor = await db.execute(query, params)
        rows = await cursor.fetchall()
        questions = [_row_to_question(row) for row in rows]
    except Exception:
        query = """
            SELECT q.id, q.user_id, q.title, q.description, q.type, q.correct_answer, q.difficulty,
                   q.explanation, q.is_public, q.is_flagged, q.likes_count, q.created_at, q.updated_at,
                   u.name,
                   EXISTS(SELECT 1 FROM question_likes l WHERE l.user_id = ? AND l.question_id = q.id) AS liked,
                   EXISTS(SELECT 1 FROM bookmarks b WHERE b.user_id = ? AND b.question_id = q.id) AS bookmarked,
                   q.image_url, q.media_url, q.attachment_url
            FROM questions q
            JOIN users u ON u.id = q.user_id
        """
        params: list = [current_user_id, current_user_id]
        if only_public:
            query += " WHERE q.is_public = 1 AND q.is_flagged = 0"
        query += " ORDER BY q.created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        cursor = await db.execute(query, params)
        rows = await cursor.fetchall()
        questions = [_row_to_question(row) for row in rows]
    for question in questions:
        question["tags"] = await _get_tags(db, question["id"])
        question["options"] = await _get_options(db, question["id"])
    return questions


async def update_question(
    db,
    question_id: int,
    title: str | None = None,
    description: str | None = None,
    type: str | None = None,
    correct_answer: str | None = None,
    difficulty: str | None = None,
    explanation: str | None = None,
    image_url: str | None = None,
    media_url: str | None = None,
    attachment_url: str | None = None,
    is_public: bool | None = None,
    tag_names: list[str] | None = None,
    options: list[dict[str, Any]] | None = None,
) -> Optional[dict]:
    current = await get_question_by_id(db, question_id)
    if current is None:
        return None
    fields = []
    values: list = []
    if title is not None:
        fields.append("title = ?")
        values.append(title)
    if description is not None:
        fields.append("description = ?")
        values.append(description)
    if type is not None:
        fields.append("type = ?")
        values.append(type)
    if correct_answer is not None:
        fields.append("correct_answer = ?")
        values.append(correct_answer)
    if difficulty is not None:
        fields.append("difficulty = ?")
        values.append(difficulty)
    if explanation is not None:
        fields.append("explanation = ?")
        values.append(explanation)
    if image_url is not None:
        fields.append("image_url = ?")
        values.append(image_url)
    if media_url is not None:
        fields.append("media_url = ?")
        values.append(media_url)
    if attachment_url is not None:
        fields.append("attachment_url = ?")
        values.append(attachment_url)
    if is_public is not None:
        fields.append("is_public = ?")
        values.append(int(is_public))
    if fields:
        values.append(question_id)
        await db.execute(f"UPDATE questions SET {', '.join(fields)}, updated_at = datetime('now') WHERE id = ?", tuple(values))

    if tag_names is not None:
        await db.execute("DELETE FROM question_tags WHERE question_id = ?", (question_id,))
        for tag_name in tag_names:
            tag_id = await _get_or_create_tag_id(db, tag_name.strip())
            await db.execute(
                "INSERT OR IGNORE INTO question_tags (question_id, tag_id) VALUES (?, ?)",
                (question_id, tag_id),
            )

    if options is not None:
        await db.execute("DELETE FROM question_options WHERE question_id = ?", (question_id,))
        for option in options:
            await db.execute(
                "INSERT INTO question_options (question_id, option_text, option_order, image_url) VALUES (?, ?, ?, ?)",
                (question_id, option["option_text"], option["option_order"], option.get("image_url")),
            )

    await db.commit()
    return await get_question_by_id(db, question_id)


async def delete_question(db, question_id: int) -> None:
    await db.execute("DELETE FROM questions WHERE id = ?", (question_id,))
    await db.execute("DELETE FROM pending_approvals WHERE content_type = 'question' AND content_id = ?", (question_id,))
    await db.commit()


async def add_like(db, user_id: int, question_id: int) -> Optional[dict]:
    question = await get_question_by_id(db, question_id)
    if question is None:
        return None

    cursor = await db.execute(
        "SELECT 1 FROM question_likes WHERE user_id = ? AND question_id = ?",
        (user_id, question_id),
    )
    if await cursor.fetchone():
        return question

    await db.execute(
        "INSERT INTO question_likes (user_id, question_id) VALUES (?, ?)",
        (user_id, question_id),
    )
    await db.execute("UPDATE questions SET likes_count = likes_count + 1 WHERE id = ?", (question_id,))
    await db.commit()
    return await get_question_by_id(db, question_id)


async def remove_like(db, user_id: int, question_id: int) -> Optional[dict]:
    question = await get_question_by_id(db, question_id)
    if question is None:
        return None

    cursor = await db.execute(
        "SELECT 1 FROM question_likes WHERE user_id = ? AND question_id = ?",
        (user_id, question_id),
    )
    if not await cursor.fetchone():
        return question

    await db.execute(
        "DELETE FROM question_likes WHERE user_id = ? AND question_id = ?",
        (user_id, question_id),
    )
    await db.execute(
        "UPDATE questions SET likes_count = CASE WHEN likes_count - 1 < 0 THEN 0 ELSE likes_count - 1 END WHERE id = ?",
        (question_id,),
    )
    await db.commit()
    return await get_question_by_id(db, question_id)


async def toggle_bookmark(db, user_id: int, question_id: int) -> dict:
    cursor = await db.execute(
        "SELECT 1 FROM bookmarks WHERE user_id = ? AND question_id = ?",
        (user_id, question_id),
    )
    existing = await cursor.fetchone()
    if existing:
        await db.execute("DELETE FROM bookmarks WHERE user_id = ? AND question_id = ?", (user_id, question_id))
        await db.commit()
        return {"bookmarked": False}
    await db.execute("INSERT INTO bookmarks (user_id, question_id) VALUES (?, ?)", (user_id, question_id))
    await db.commit()
    return {"bookmarked": True}
