import json
import random
from typing import Any, Dict

from fastapi import HTTPException, status

try:
    from backend.models import exam_model
    from backend.services import leaderboard_service, notification_service, achievement_service
except ImportError:
    from models import exam_model
    from services import leaderboard_service, notification_service, achievement_service


async def score_exam(db, exam_id: int, answers: dict[str, Any]) -> dict[str, Any]:
    cursor = await db.execute(
        "SELECT q.id, q.correct_answer, eq.marks FROM exam_questions eq JOIN questions q ON q.id = eq.question_id WHERE eq.exam_id = ?",
        (exam_id,),
    )
    rows = await cursor.fetchall()
    total_marks = 0
    score = 0
    breakdown: list[dict[str, Any]] = []
    normalized_answers = {str(k): str(v).strip() for k, v in answers.items()}

    for row in rows:
        question_id = row[0]
        correct_answer = row[1] or ""
        marks = row[2]
        total_marks += marks
        given_answer = normalized_answers.get(str(question_id), "").strip()
        earned = 1 if given_answer and given_answer.lower() == str(correct_answer).strip().lower() else 0
        if earned:
            score += marks
        breakdown.append({
            "question_id": question_id,
            "given_answer": given_answer,
            "correct_answer": correct_answer,
            "marks": marks,
            "earned": earned,
        })

    return {"score": score, "total_marks": total_marks, "breakdown": breakdown}


async def start_exam_attempt(db, exam_id: int, user_id: int) -> dict[str, Any]:
    exam = await exam_model.get_exam_by_id(db, exam_id)
    if exam is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Exam not found")
    attempt = await exam_model.get_latest_active_attempt(db, exam_id, user_id)
    if attempt is not None:
        return attempt

    question_order = exam["questions"].copy()
    if exam.get("randomize_order"):
        random.shuffle(question_order)
        for index, item in enumerate(question_order, start=1):
            item["question_order"] = index

    attempt = await exam_model.create_attempt(db, exam_id, user_id, question_order=question_order)
    if attempt is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not start exam attempt")
    return attempt


async def save_exam_attempt_progress(db, attempt_id: int, user_id: int, time_taken_seconds: int, answers: dict[str, Any]) -> dict[str, Any]:
    attempt = await exam_model.get_attempt(db, attempt_id)
    if attempt is None or attempt["user_id"] != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attempt not found")
    exam = await exam_model.get_exam_by_id(db, attempt["exam_id"])
    if exam is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Exam not found")
    max_time = exam["duration_minutes"] * 60 + 30
    if time_taken_seconds > max_time:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Time limit exceeded: {time_taken_seconds}s > allowed {max_time}s",
        )
    saved = await exam_model.save_attempt_progress(db, attempt_id, user_id, answers, time_taken_seconds)
    if saved is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not save attempt progress")
    return saved


async def submit_exam_attempt(db, attempt_id: int, user_id: int, time_taken_seconds: int, answers: dict[str, Any]) -> dict[str, Any]:
    attempt = await exam_model.get_attempt(db, attempt_id)
    if attempt is None or attempt["user_id"] != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attempt not found")

    exam = await exam_model.get_exam_by_id(db, attempt["exam_id"])
    if exam is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Exam not found")

    max_time = exam["duration_minutes"] * 60 + 30
    if time_taken_seconds > max_time:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Time limit exceeded: {time_taken_seconds}s > allowed {max_time}s",
        )

    scoring = await score_exam(db, exam["id"], answers)
    attempt = await exam_model.submit_attempt(db, attempt_id, user_id, scoring["score"], time_taken_seconds, answers)

    if attempt["attempt_number"] == 1:
        await leaderboard_service.insert_leaderboard_entry(
            db,
            exam_id=exam["id"],
            user_id=user_id,
            attempt_id=attempt["id"],
            score=attempt["score"],
            time_taken_seconds=attempt["time_taken_seconds"],
        )
        await leaderboard_service.recompute_ranks(db, exam["id"])
        board = await leaderboard_service.get_exam_leaderboard(db, exam["id"])
        rank_entry = next((entry for entry in board if entry["user_id"] == user_id), None)
        if rank_entry:
            message = f"Your first submission for exam '{exam['title']}' ranked #{rank_entry['rank']}"
            await notification_service.create_notification(
                db,
                exam["user_id"],
                "exam_ranked",
                message,
                attempt["id"],
                "exam_attempt",
            )

    await achievement_service.award_badges(db, user_id)
    return attempt


async def notify_new_exam(db, exam: dict[str, Any]) -> None:
    if not exam.get("is_public"):
        return
    cursor = await db.execute("SELECT id FROM users WHERE role = 'student'")
    rows = await cursor.fetchall()
    for row in rows:
        student_id = row[0]
        message = f"New public exam available: {exam['title']}"
        await notification_service.create_notification(db, student_id, "exam_created", message, exam["id"], "exam")
    await db.commit()
