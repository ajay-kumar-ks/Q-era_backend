from typing import Any
from fastapi import HTTPException

try:
    from backend.models import question_model, comment_model
    from backend.services import ai_service, notification_service, achievement_service
except ImportError:
    from models import question_model, comment_model
    from services import ai_service, notification_service, achievement_service
from fastapi import HTTPException


async def create_question(
    db,
    user_id: int,
    title: str,
    description: str | None,
    type: str,
    correct_answer: str | None,
    difficulty: str | None,
    explanation: str | None,
    image_url: str | None,
    media_url: str | None,
    attachment_url: str | None,
    is_public: bool,
    tags: list[str] | None,
    options: list[dict[str, Any]] | None,
    requires_approval: bool = False,
) -> dict[str, Any]:
    tags = tags or []
    options = options or []

    duplicate_result = await ai_service.check_duplicate(db, title, description)
    if not tags:
        tags = await ai_service.suggest_tags(db, title, description)
    if not difficulty:
        difficulty_result = await ai_service.analyze_difficulty(db, title, description)
        difficulty = difficulty_result['difficulty']
    question = await question_model.create_question(
        db,
        user_id=user_id,
        title=title,
        description=description,
        type=type,
        correct_answer=correct_answer,
        difficulty=difficulty,
        explanation=explanation,
        image_url=image_url,
        media_url=media_url,
        attachment_url=attachment_url,
        is_public=is_public,
        tag_names=tags,
        options=options,
        requires_approval=requires_approval,
    )

    if question is None:
        raise HTTPException(status_code=500, detail="Failed to create question.")

    if question['is_public'] and not question.get('requires_approval', False):
        await notify_new_question(db, question)

    await achievement_service.award_badges(db, user_id)
    question['duplicate_warning'] = duplicate_result if duplicate_result['is_duplicate'] else None
    return question


async def notify_new_question(db, question: dict[str, Any]) -> None:
    if not question.get("is_public"):
        return
    cursor = await db.execute("SELECT id FROM users WHERE role = 'student'")
    rows = await cursor.fetchall()
    for row in rows:
        student_id = row[0]
        message = f"New public question available: {question['title']}"
        await notification_service.create_notification(db, student_id, "question_created", message, question['id'], "question")


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
    tags: list[str] | None = None,
    options: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    return await question_model.update_question(
        db,
        question_id,
        title=title,
        description=description,
        type=type,
        correct_answer=correct_answer,
        difficulty=difficulty,
        explanation=explanation,
        image_url=image_url,
        media_url=media_url,
        attachment_url=attachment_url,
        is_public=is_public,
        tag_names=tags,
        options=options,
    )


async def get_question(db, question_id: int, current_user_id: int | None = None) -> dict[str, Any] | None:
    return await question_model.get_question_by_id(db, question_id, current_user_id=current_user_id)


async def list_questions(db, page: int = 1, limit: int = 20, current_user_id: int | None = None) -> list[dict[str, Any]]:
    return await question_model.list_questions(db, page=page, limit=limit, only_public=True, current_user_id=current_user_id)


async def delete_question(db, question_id: int) -> None:
    await question_model.delete_question(db, question_id)


async def like_question(db, question_id: int, user_id: int) -> dict[str, Any] | None:
    cursor = await db.execute(
        "SELECT 1 FROM question_likes WHERE user_id = ? AND question_id = ?",
        (user_id, question_id),
    )
    existing = await cursor.fetchone()
    if existing:
        return await question_model.remove_like(db, user_id, question_id)
    return await question_model.add_like(db, user_id, question_id)


async def toggle_bookmark(db, user_id: int, question_id: int) -> dict[str, Any]:
    return await question_model.toggle_bookmark(db, user_id, question_id)


async def create_comment(db, question_id: int, user_id: int, content: str, parent_id: int | None = None) -> dict[str, Any]:
    comment = await comment_model.create_comment(db, question_id, user_id, content, parent_id)
    if parent_id is not None:
        cursor = await db.execute("SELECT user_id FROM comments WHERE id = ?", (parent_id,))
        row = await cursor.fetchone()
        if row and row[0] != user_id:
            message = "Someone replied to your comment."
            await notification_service.create_notification(db, row[0], 'comment_reply', message, comment['id'], 'comment')
    else:
        cursor = await db.execute("SELECT user_id FROM questions WHERE id = ?", (question_id,))
        row = await cursor.fetchone()
        if row and row[0] != user_id:
            message = "Someone commented on your question."
            await notification_service.create_notification(db, row[0], 'question_comment', message, comment['id'], 'comment')
    return comment


async def list_comments(db, question_id: int, sort_by: str = "newest") -> list[dict[str, Any]]:
    return await comment_model.get_comments_by_question(db, question_id, sort_by=sort_by)
