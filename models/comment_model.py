from typing import Optional


def _row_to_comment(row) -> dict:
    return {
        "id": row[0],
        "question_id": row[1],
        "user_id": row[2],
        "parent_id": row[3],
        "content": row[4],
        "is_flagged": bool(row[5]),
        "upvotes_count": row[6] if len(row) > 6 else 0,
        "is_helpful": bool(row[7] if len(row) > 7 else 0),
        "created_at": row[8] if len(row) > 8 else row[6],
        "upvoted": bool(row[9] if len(row) > 9 else 0),
        "replies": [],
    }


async def create_comment(db, question_id: int, user_id: int, content: str, parent_id: int | None = None) -> dict:
    cursor = await db.execute(
        "INSERT INTO comments (question_id, user_id, parent_id, content) VALUES (?, ?, ?, ?)",
        (question_id, user_id, parent_id, content),
    )
    await db.commit()
    comment_id = cursor.lastrowid
    return await get_comment_by_id(db, comment_id, user_id)


async def get_comment_by_id(db, comment_id: int, current_user_id: int | None = None) -> Optional[dict]:
    current_user_id = current_user_id if current_user_id is not None else -1
    cursor = await db.execute(
        """
        SELECT c.id, c.question_id, c.user_id, c.parent_id, c.content, c.is_flagged,
               c.upvotes_count, c.is_helpful, c.created_at,
               EXISTS(SELECT 1 FROM comment_votes v WHERE v.user_id = ? AND v.comment_id = c.id) AS upvoted
        FROM comments c
        WHERE c.id = ?
        """,
        (current_user_id, comment_id),
    )
    row = await cursor.fetchone()
    if row is None:
        return None
    return _row_to_comment(row)


async def get_comments_by_question(
    db,
    question_id: int,
    current_user_id: int | None = None,
    include_flagged: bool = False,
    sort_by: str = "newest",
) -> list[dict]:
    current_user_id = current_user_id if current_user_id is not None else -1
    order_clause = (
        "c.created_at DESC"
        if sort_by == "newest"
        else "c.upvotes_count DESC, c.is_helpful DESC, c.created_at DESC"
    )
    query = """
        SELECT c.id, c.question_id, c.user_id, c.parent_id, c.content, c.is_flagged,
               c.upvotes_count, c.is_helpful, c.created_at,
               EXISTS(SELECT 1 FROM comment_votes v WHERE v.user_id = ? AND v.comment_id = c.id) AS upvoted
        FROM comments c
        WHERE c.question_id = ?
    """
    params = [current_user_id, question_id]
    if not include_flagged:
        query += " AND c.is_flagged = 0"
    query += f" ORDER BY {order_clause}"
    cursor = await db.execute(query, params)
    rows = await cursor.fetchall()
    comments = [_row_to_comment(row) for row in rows]
    return _nest_comments(comments)


async def add_comment_vote(db, comment_id: int, user_id: int) -> Optional[dict]:
    cursor = await db.execute(
        "SELECT 1 FROM comment_votes WHERE user_id = ? AND comment_id = ?",
        (user_id, comment_id),
    )
    if await cursor.fetchone():
        return None

    await db.execute(
        "INSERT INTO comment_votes (user_id, comment_id) VALUES (?, ?)",
        (user_id, comment_id),
    )
    await db.execute("UPDATE comments SET upvotes_count = upvotes_count + 1 WHERE id = ?", (comment_id,))
    await db.commit()
    return await get_comment_by_id(db, comment_id, user_id)


async def mark_comment_helpful(db, comment_id: int) -> Optional[dict]:
    await db.execute("UPDATE comments SET is_helpful = 1 WHERE id = ?", (comment_id,))
    await db.commit()
    return await get_comment_by_id(db, comment_id, None)


async def flag_comment(db, comment_id: int) -> dict | None:
    """Set is_flagged=1 for a comment and return the updated comment, or None if not found."""
    await db.execute("UPDATE comments SET is_flagged = 1 WHERE id = ?", (comment_id,))
    await db.commit()
    return await get_comment_by_id(db, comment_id, None)


def _nest_comments(flat_comments: list[dict]) -> list[dict]:
    comments_by_id = {comment["id"]: comment for comment in flat_comments}
    root_comments = []
    for comment in flat_comments:
        if comment["parent_id"] and comment["parent_id"] in comments_by_id:
            comments_by_id[comment["parent_id"]]["replies"].append(comment)
        else:
            root_comments.append(comment)
    return root_comments
