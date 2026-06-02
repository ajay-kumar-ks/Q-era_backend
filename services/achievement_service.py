from typing import Any, Dict, List

try:
    from backend.models import badge_model
    from backend.services import notification_service
except ImportError:
    from models import badge_model
    from services import notification_service


async def _fetch_user_stats(db, user_id: int) -> Dict[str, Any]:
    cursor = await db.execute(
        "SELECT COUNT(*) FROM exam_attempts WHERE user_id = ? AND status = 'submitted'",
        (user_id,),
    )
    exams_completed = (await cursor.fetchone())[0] or 0

    cursor = await db.execute(
        "SELECT COUNT(*) FROM questions WHERE user_id = ?",
        (user_id,),
    )
    questions_created = (await cursor.fetchone())[0] or 0

    cursor = await db.execute(
        "SELECT MAX(score) FROM exam_attempts WHERE user_id = ? AND status = 'submitted'",
        (user_id,),
    )
    max_score_row = await cursor.fetchone()
    max_score = max_score_row[0] or 0

    return {
        "exams_completed": exams_completed,
        "questions_created": questions_created,
        "max_score": max_score,
    }


async def award_badges(db, user_id: int) -> List[Dict[str, Any]]:
    unearned = await badge_model.get_unearned_badges(db, user_id)
    if not unearned:
        return []

    stats = await _fetch_user_stats(db, user_id)
    unlocked: List[Dict[str, Any]] = []

    for badge in unearned:
        earned = False
        if badge["criteria_type"] == "exams_completed":
            earned = stats["exams_completed"] >= badge["criteria_value"]
        elif badge["criteria_type"] == "questions_created":
            earned = stats["questions_created"] >= badge["criteria_value"]
        elif badge["criteria_type"] == "score_threshold":
            earned = stats["max_score"] >= badge["criteria_value"]

        if not earned:
            continue

        if await badge_model.unlock_badge(db, user_id, badge["id"]):
            unlocked.append(badge)
            await notification_service.create_notification(
                db,
                user_id,
                "achievement_unlocked",
                f"Congratulations! You've earned the '{badge['name']}' badge.",
                badge["id"],
                "badge",
            )

    return unlocked
