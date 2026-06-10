from fastapi import APIRouter, Depends, HTTPException, Request, status

try:
    from backend.schemas.user_schema import BadgeOut, UserProfileOut, UserUpdate
    from backend.models import user_model
    from backend.models.badge_model import get_user_badges
    from backend.models.notification_model import get_notifications_for_user, mark_notification_read, mark_all_notifications_read
    from backend.middlewares.auth import get_current_user
    from backend.services import ai_service
except ImportError:
    from schemas.user_schema import BadgeOut, UserProfileOut, UserUpdate
    from models import user_model
    from models.badge_model import get_user_badges
    from models.notification_model import get_notifications_for_user, mark_notification_read, mark_all_notifications_read
    from middlewares.auth import get_current_user
    from services import ai_service

router = APIRouter(prefix="/api/v1", tags=["users"])


@router.get("/users/me", response_model=UserProfileOut)
async def read_my_profile(request: Request, current_user: dict = Depends(get_current_user)):
    db = request.app.state.db
    profile = await user_model.get_user_profile(db, current_user["id"])
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User profile not found")
    return profile


@router.get("/users/{user_id}", response_model=UserProfileOut)
async def read_user_profile(request: Request, user_id: int):
    db = request.app.state.db
    profile = await user_model.get_user_profile(db, user_id)
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return profile


@router.put("/users/me", response_model=UserProfileOut)
async def update_my_profile(request: Request, payload: UserUpdate, current_user: dict = Depends(get_current_user)):
    db = request.app.state.db

    # Moderate bio and display_name before saving (fail-open)
    fields_to_moderate = {
        "bio": payload.bio,
        "display_name": payload.name,
    }
    for field_name, field_value in fields_to_moderate.items():
        if field_value:
            mod_result = await ai_service.moderation_filter(field_value)
            if mod_result.get("is_toxic") or mod_result.get("is_spam"):
                raise HTTPException(
                    status_code=400,
                    detail=f"Profile {field_name} rejected by content moderation: {mod_result.get('reason', 'Policy violation')}",
                )

    updated = await user_model.update_user(
        db,
        current_user["id"],
        name=payload.name,
        avatar_url=payload.avatar_url,
        bio=payload.bio,
        preferred_topics=payload.preferred_topics,
        learning_goals=payload.learning_goals,
        notification_preferences=payload.notification_preferences,
    )
    if updated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    profile = await user_model.get_user_profile(db, current_user["id"])
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User profile not found")
    return profile


@router.get("/users/me/bookmarks")
async def read_my_bookmarks(request: Request, current_user: dict = Depends(get_current_user)):
    db = request.app.state.db
    return await user_model.get_user_bookmarks(db, current_user["id"])


@router.get("/users/me/questions")
async def read_my_questions(request: Request, page: int = 1, limit: int = 10, current_user: dict = Depends(get_current_user)):
    db = request.app.state.db
    return await user_model.get_user_questions(db, current_user["id"], page=page, limit=limit)


@router.get("/users/me/exams")
async def read_my_exams(request: Request, page: int = 1, limit: int = 10, current_user: dict = Depends(get_current_user)):
    db = request.app.state.db
    return await user_model.get_user_exams(db, current_user["id"], page=page, limit=limit)


@router.get("/users/me/progress")
async def read_my_progress(request: Request, current_user: dict = Depends(get_current_user)):
    db = request.app.state.db
    return await user_model.get_learning_progress(db, current_user["id"])


@router.get("/users/me/notifications")
async def read_my_notifications(request: Request, current_user: dict = Depends(get_current_user)):
    db = request.app.state.db
    return await get_notifications_for_user(db, current_user["id"])


@router.get("/users/me/badges", response_model=list[BadgeOut])
async def read_my_badges(request: Request, current_user: dict = Depends(get_current_user)):
    db = request.app.state.db
    return await get_user_badges(db, current_user["id"])


@router.get("/users/{user_id}/badges", response_model=list[BadgeOut])
async def read_user_badges(request: Request, user_id: int):
    db = request.app.state.db
    return await get_user_badges(db, user_id)


@router.put("/users/me/notifications/{notification_id}/read")
async def mark_my_notification_read(request: Request, notification_id: int, current_user: dict = Depends(get_current_user)):
    db = request.app.state.db
    notification = await mark_notification_read(db, notification_id, current_user["id"])
    if notification is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")
    return notification


@router.put("/users/me/notifications/read-all")
async def mark_my_notifications_read(request: Request, current_user: dict = Depends(get_current_user)):
    db = request.app.state.db
    updated = await mark_all_notifications_read(db, current_user["id"])
    return {"updated": updated}
