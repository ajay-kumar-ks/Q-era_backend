from typing import Optional


async def create_notification(
    db,
    user_id: int,
    type: str,
    message: str,
    reference_id: Optional[int] = None,
    reference_type: Optional[str] = None,
) -> None:
    await db.execute(
        "INSERT INTO notifications (user_id, type, message, reference_id, reference_type) VALUES (?, ?, ?, ?, ?)",
        (user_id, type, message, reference_id, reference_type),
    )
    await db.commit()
