from typing import Any, Dict, List, Optional


def _row_to_notification(row) -> Dict[str, Any]:
    return {
        "id": row[0],
        "user_id": row[1],
        "type": row[2],
        "message": row[3],
        "reference_id": row[4],
        "reference_type": row[5],
        "is_read": bool(row[6]),
        "created_at": row[7],
    }


async def get_notifications_for_user(db, user_id: int) -> List[Dict[str, Any]]:
    cursor = await db.execute(
        "SELECT id, user_id, type, message, reference_id, reference_type, is_read, created_at FROM notifications WHERE user_id = ? ORDER BY created_at DESC",
        (user_id,),
    )
    rows = await cursor.fetchall()
    return [_row_to_notification(row) for row in rows]


async def mark_notification_read(db, notification_id: int, user_id: int) -> Optional[Dict[str, Any]]:
    await db.execute(
        "UPDATE notifications SET is_read = 1 WHERE id = ? AND user_id = ?",
        (notification_id, user_id),
    )
    await db.commit()
    cursor = await db.execute(
        "SELECT id, user_id, type, message, reference_id, reference_type, is_read, created_at FROM notifications WHERE id = ? AND user_id = ?",
        (notification_id, user_id),
    )
    row = await cursor.fetchone()
    if row is None:
        return None
    return _row_to_notification(row)


async def mark_all_notifications_read(db, user_id: int) -> int:
    cursor = await db.execute(
        "UPDATE notifications SET is_read = 1 WHERE user_id = ? AND is_read = 0",
        (user_id,),
    )
    await db.commit()
    return cursor.rowcount
