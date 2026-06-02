from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File, status
from fastapi.concurrency import run_in_threadpool
from typing import Optional

try:
    from backend.schemas.question_schema import QuestionCreate, QuestionOut, QuestionUpdate
    from backend.services.question_service import create_question, delete_question, get_question, list_questions, like_question, toggle_bookmark, update_question
    from backend.middlewares.auth import get_current_user, get_current_user_optional
except ImportError:
    from schemas.question_schema import QuestionCreate, QuestionOut, QuestionUpdate
    from services.question_service import create_question, delete_question, get_question, list_questions, like_question, toggle_bookmark, update_question
    from middlewares.auth import get_current_user, get_current_user_optional

router = APIRouter(prefix="/api/v1/questions", tags=["questions"])


@router.get("/", response_model=list[QuestionOut])
async def read_questions(request: Request, page: int = 1, limit: int = 20, current_user: dict | None = Depends(get_current_user_optional)):
    db = request.app.state.db
    return await list_questions(db, page=page, limit=limit, current_user_id=current_user and current_user.get("id"))


@router.get("/{question_id}", response_model=QuestionOut)
async def read_question(request: Request, question_id: int, current_user: dict | None = Depends(get_current_user_optional)):
    db = request.app.state.db
    question = await get_question(db, question_id, current_user_id=current_user and current_user.get("id"))
    if question is None or question.get("is_flagged"):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Question not found")
    return question


@router.post("/", response_model=QuestionOut, status_code=status.HTTP_201_CREATED)
async def create_new_question(request: Request, payload: QuestionCreate, current_user: dict = Depends(get_current_user)):
    db = request.app.state.db
    question = await create_question(
        db,
        user_id=current_user["id"],
        title=payload.title,
        description=payload.description,
        type=payload.type,
        correct_answer=payload.correct_answer,
        difficulty=payload.difficulty,
        explanation=payload.explanation,
        image_url=payload.image_url,
        media_url=payload.media_url,
        attachment_url=payload.attachment_url,
        is_public=payload.is_public,
        tags=payload.tags,
        options=[option.model_dump() for option in payload.options],
        requires_approval=current_user["role"] != "admin",
    )
    return question


try:
    from backend.services.cloudinary_service import upload_to_cloudinary
except ImportError:
    from services.cloudinary_service import upload_to_cloudinary


@router.post("/upload-media")
async def upload_media(request: Request, file: UploadFile = File(...), current_user: dict = Depends(get_current_user)):
    db = request.app.state.db
    try:
        file_bytes = await file.read()
        upload_result = await run_in_threadpool(upload_to_cloudinary, file.filename, file_bytes, file.content_type)
        return {
            "url": upload_result["secure_url"],
            "public_id": upload_result.get("public_id"),
        }
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.put("/{question_id}", response_model=QuestionOut)
async def edit_question(request: Request, question_id: int, payload: QuestionUpdate, current_user: dict = Depends(get_current_user)):
    db = request.app.state.db
    question = await get_question(db, question_id, current_user_id=current_user["id"])
    if question is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Question not found")
    if current_user["role"] != "admin" and question["user_id"] != current_user["id"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to edit this question")
    updated = await update_question(
        db,
        question_id,
        title=payload.title,
        description=payload.description,
        type=payload.type,
        correct_answer=payload.correct_answer,
        difficulty=payload.difficulty,
        explanation=payload.explanation,
        image_url=payload.image_url,
        media_url=payload.media_url,
        attachment_url=payload.attachment_url,
        is_public=payload.is_public,
        tags=payload.tags,
        options=[option.model_dump() for option in payload.options] if payload.options is not None else None,
    )
    if updated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Question not found")
    return updated


@router.delete("/{question_id}")
async def remove_question(request: Request, question_id: int, current_user: dict = Depends(get_current_user)):
    db = request.app.state.db
    question = await get_question(db, question_id, current_user_id=current_user["id"])
    if question is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Question not found")
    if current_user["role"] != "admin" and question["user_id"] != current_user["id"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to delete this question")
    await delete_question(db, question_id)
    return {"message": "Question deleted successfully"}


@router.post("/{question_id}/like")
async def like_question_endpoint(request: Request, question_id: int, current_user: dict = Depends(get_current_user)):
    db = request.app.state.db
    question = await like_question(db, question_id, current_user["id"])
    if question is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Question not found")
    return question


@router.post("/{question_id}/bookmark")
async def bookmark_question(request: Request, question_id: int, current_user: dict = Depends(get_current_user)):
    db = request.app.state.db
    return await toggle_bookmark(db, current_user["id"], question_id)
