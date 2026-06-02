from fastapi import APIRouter, Depends, HTTPException, Request, status

try:
    from backend.models.notification_model import get_notifications_for_user, mark_notification_read, mark_all_notifications_read
    from backend.middlewares.auth import get_current_user
except ImportError:
    from models.notification_model import get_notifications_for_user, mark_notification_read, mark_all_notifications_read
    from middlewares.auth import get_current_user

router = APIRouter(prefix="/api/v1", tags=["notifications"])


@router.get("/notifications/")
async def read_notifications(request: Request, current_user: dict = Depends(get_current_user)):
    db = request.app.state.db
    items = await get_notifications_for_user(db, current_user["id"])
    unread = sum(1 for it in items if not it.get("is_read"))
    return {"unread_count": unread, "items": items}


@router.put("/notifications/{notification_id}/read")
async def mark_notification_read_endpoint(request: Request, notification_id: int, current_user: dict = Depends(get_current_user)):
    db = request.app.state.db
    notification = await mark_notification_read(db, notification_id, current_user["id"])
    if notification is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")
    return notification


@router.put("/notifications/read-all")
async def mark_all_notifications_read_endpoint(request: Request, current_user: dict = Depends(get_current_user)):
    db = request.app.state.db
    updated = await mark_all_notifications_read(db, current_user["id"])
    return {"updated": updated}
