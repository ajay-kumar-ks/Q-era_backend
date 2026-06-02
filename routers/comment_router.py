from fastapi import APIRouter, Depends, HTTPException, Request, status

try:
    from backend.schemas.question_schema import CommentCreate, CommentOut
    from backend.services.question_service import create_comment, list_comments, get_question
    from backend.models import comment_model
    from backend.middlewares.auth import get_current_user
except ImportError:
    from schemas.question_schema import CommentCreate, CommentOut
    from services.question_service import create_comment, list_comments, get_question
    from models import comment_model
    from middlewares.auth import get_current_user

router = APIRouter(prefix="/api/v1/questions", tags=["comments"])


@router.get("/{question_id}/comments", response_model=list[CommentOut])
async def read_comments(request: Request, question_id: int, sort_by: str = "newest"):
    db = request.app.state.db
    question = await get_question(db, question_id)
    if question is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Question not found")
    return await list_comments(db, question_id, sort_by=sort_by)


@router.post("/{question_id}/comments", response_model=CommentOut)
async def create_question_comment(request: Request, question_id: int, payload: CommentCreate, current_user: dict = Depends(get_current_user)):
    db = request.app.state.db
    question = await get_question(db, question_id)
    if question is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Question not found")
    return await create_comment(db, question_id, current_user["id"], payload.content)


@router.post("/{question_id}/comments/{comment_id}/reply", response_model=CommentOut)
async def reply_to_comment(request: Request, question_id: int, comment_id: int, payload: CommentCreate, current_user: dict = Depends(get_current_user)):
    db = request.app.state.db
    question = await get_question(db, question_id)
    if question is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Question not found")
    return await create_comment(db, question_id, current_user["id"], payload.content, parent_id=comment_id)


@router.post("/{question_id}/comments/{comment_id}/upvote", response_model=CommentOut)
async def upvote_comment(request: Request, question_id: int, comment_id: int, current_user: dict = Depends(get_current_user)):
    db = request.app.state.db
    question = await get_question(db, question_id)
    if question is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Question not found")

    cursor = await db.execute("SELECT question_id FROM comments WHERE id = ?", (comment_id,))
    row = await cursor.fetchone()
    if row is None or row[0] != question_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found")

    comment = await comment_model.add_comment_vote(db, comment_id, current_user["id"])
    if comment is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Already upvoted this comment")
    return comment


@router.put("/{question_id}/comments/{comment_id}/helpful", response_model=CommentOut)
async def mark_comment_helpful(request: Request, question_id: int, comment_id: int, current_user: dict = Depends(get_current_user)):
    db = request.app.state.db
    question = await get_question(db, question_id)
    if question is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Question not found")

    if question["user_id"] != current_user["id"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the question author can mark helpful replies")

    cursor = await db.execute("SELECT question_id FROM comments WHERE id = ?", (comment_id,))
    row = await cursor.fetchone()
    if row is None or row[0] != question_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found")

    comment = await comment_model.mark_comment_helpful(db, comment_id)
    if comment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found")
    return comment


@router.post("/{question_id}/comments/{comment_id}/flag")
async def flag_comment_endpoint(request: Request, question_id: int, comment_id: int, current_user: dict = Depends(get_current_user)):
    db = request.app.state.db
    question = await get_question(db, question_id)
    if question is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Question not found")

    cursor = await db.execute("SELECT question_id FROM comments WHERE id = ?", (comment_id,))
    row = await cursor.fetchone()
    if row is None or row[0] != question_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found")

    comment = await comment_model.flag_comment(db, comment_id)
    if comment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found")
    return comment
