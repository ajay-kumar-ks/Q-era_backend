"""Review Router - Endpoints for spaced repetition and review management"""
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

try:
    from backend.models import review_schedule_model
    from backend.middlewares.auth import get_current_user
except ImportError:
    from models import review_schedule_model
    from middlewares.auth import get_current_user


router = APIRouter(prefix="/api/v1/review", tags=["review"])


# Pydantic models
class ReviewAttempt(BaseModel):
    question_id: int
    user_answer: str
    is_correct: bool
    time_spent_seconds: int = 0


class ReviewResponse(BaseModel):
    id: int
    question_id: int
    next_review_at: str
    review_count: int
    status: str
    ease_factor: float


@router.get("/scheduled")
async def get_scheduled_reviews(
    request: Request,
    current_user: dict = Depends(get_current_user),
    limit: int = 20,
):
    """Get questions due for review"""
    db = request.app.state.db
    print(f"DEBUG: Getting scheduled reviews for user_id={current_user.get('id')} ({current_user.get('name')})")
    reviews = await review_schedule_model.get_due_reviews(
        db, current_user["id"], limit=limit
    )
    print(f"DEBUG: Found {len(reviews)} reviews")
    return reviews


@router.get("/all")
async def get_all_reviews(
    request: Request,
    current_user: dict = Depends(get_current_user),
    status_filter: str = "pending",
    limit: int = 50,
):
    """Get all review schedules for current user"""
    db = request.app.state.db
    print(f"DEBUG: Getting all reviews for user_id={current_user.get('id')}, status={status_filter}")
    reviews = await review_schedule_model.get_all_review_schedules(
        db, current_user["id"], status=status_filter, limit=limit
    )
    return reviews


@router.get("/statistics")
async def get_review_statistics(
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Get review statistics for current user"""
    db = request.app.state.db
    print(f"DEBUG: Getting stats for user_id={current_user.get('id')}")
    stats = await review_schedule_model.get_review_statistics(db, current_user["id"])
    print(f"DEBUG: Stats result: {stats}")
    return stats


@router.get("/history")
async def get_review_history(
    request: Request,
    current_user: dict = Depends(get_current_user),
    question_id: int | None = None,
    limit: int = 20,
):
    """Get review history for current user"""
    db = request.app.state.db
    history = await review_schedule_model.get_review_history(
        db, current_user["id"], question_id=question_id, limit=limit
    )
    return history


@router.post("/attempt/{review_schedule_id}")
async def record_review_attempt(
    request: Request,
    review_schedule_id: int,
    payload: ReviewAttempt,
    current_user: dict = Depends(get_current_user),
):
    """Record a review attempt and update schedule"""
    db = request.app.state.db

    # Verify the review schedule belongs to the user
    cursor = await db.execute(
        "SELECT user_id FROM review_schedules WHERE id = ?",
        (review_schedule_id,),
    )
    row = await cursor.fetchone()
    if not row or row[0] != current_user["id"]:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Review schedule not found",
        )

    result = await review_schedule_model.record_review_attempt(
        db,
        review_schedule_id=review_schedule_id,
        user_id=current_user["id"],
        question_id=payload.question_id,
        user_answer=payload.user_answer,
        is_correct=payload.is_correct,
        time_spent_seconds=payload.time_spent_seconds,
    )

    return result


@router.get("/question/{question_id}")
async def get_question_review_schedule(
    request: Request,
    question_id: int,
    current_user: dict = Depends(get_current_user),
):
    """Get review schedule for a specific question"""
    db = request.app.state.db
    schedule = await review_schedule_model.get_review_schedule(
        db, current_user["id"], question_id
    )

    if not schedule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No review schedule found for this question",
        )

    return schedule
