from typing import Any, Dict, List


def _row_to_badge(row) -> Dict[str, Any]:
    return {
        "id": row[0],
        "name": row[1],
        "description": row[2],
        "icon_url": row[3],
        "criteria_type": row[4],
        "criteria_value": row[5],
        "unlocked_at": row[6],
    }


async def get_user_badges(db, user_id: int) -> List[Dict[str, Any]]:
    cursor = await db.execute(
        """
        SELECT b.id, b.name, b.description, b.icon_url, b.criteria_type, b.criteria_value, ub.unlocked_at
        FROM badges b
        JOIN user_badges ub ON b.id = ub.badge_id
        WHERE ub.user_id = ?
        ORDER BY ub.unlocked_at DESC
        """,
        (user_id,),
    )
    rows = await cursor.fetchall()
    return [_row_to_badge(row) for row in rows]


async def get_unearned_badges(db, user_id: int) -> List[Dict[str, Any]]:
    cursor = await db.execute(
        """
        SELECT b.id, b.name, b.description, b.icon_url, b.criteria_type, b.criteria_value
        FROM badges b
        WHERE b.id NOT IN (SELECT badge_id FROM user_badges WHERE user_id = ?)
        """,
        (user_id,),
    )
    rows = await cursor.fetchall()
    return [
        {
            "id": row[0],
            "name": row[1],
            "description": row[2],
            "icon_url": row[3],
            "criteria_type": row[4],
            "criteria_value": row[5],
        }
        for row in rows
    ]


async def unlock_badge(db, user_id: int, badge_id: int) -> bool:
    await db.execute(
        "INSERT OR IGNORE INTO user_badges (user_id, badge_id) VALUES (?, ?)",
        (user_id, badge_id),
    )
    await db.commit()
    cursor = await db.execute(
        "SELECT 1 FROM user_badges WHERE user_id = ? AND badge_id = ?",
        (user_id, badge_id),
    )
    return bool(await cursor.fetchone())
