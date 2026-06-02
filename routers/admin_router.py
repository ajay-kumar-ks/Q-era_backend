from fastapi import APIRouter, Depends, HTTPException, Request, status

try:
    from backend.services import ai_service
    from backend.middlewares.auth import get_current_user
    from backend.middlewares.role import require_admin
    from backend.models import exam_model
except ImportError:
    from services import ai_service
    from middlewares.auth import get_current_user
    from middlewares.role import require_admin
    from models import exam_model

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


@router.get("/users")
async def list_users(request: Request, current_user: dict = Depends(get_current_user), _: dict = Depends(require_admin)):
    db = request.app.state.db
    cursor = await db.execute(
        "SELECT id, name, email, role, is_suspended, avatar_url, bio, created_at, updated_at FROM users ORDER BY created_at DESC"
    )
    rows = await cursor.fetchall()
    return [
        {
            "id": row[0],
            "name": row[1],
            "email": row[2],
            "role": row[3],
            "is_suspended": bool(row[4]),
            "avatar_url": row[5],
            "bio": row[6],
            "created_at": row[7],
            "updated_at": row[8],
        }
        for row in rows
    ]


@router.get("/stats")
async def get_admin_stats(request: Request, current_user: dict = Depends(get_current_user), _: dict = Depends(require_admin)):
    db = request.app.state.db
    
    user_count = await db.execute("SELECT COUNT(*) FROM users")
    question_count = await db.execute("SELECT COUNT(*) FROM questions")
    exam_count = await db.execute("SELECT COUNT(*) FROM exams")
    flagged_questions = await db.execute("SELECT COUNT(*) FROM questions WHERE is_flagged = 1")
    flagged_comments = await db.execute("SELECT COUNT(*) FROM comments WHERE is_flagged = 1")
    
    return {
        "total_users": (await user_count.fetchone())[0],
        "total_questions": (await question_count.fetchone())[0],
        "total_exams": (await exam_count.fetchone())[0],
        "flagged_questions": (await flagged_questions.fetchone())[0],
        "flagged_comments": (await flagged_comments.fetchone())[0],
    }


@router.put("/users/{user_id}/suspend")
async def suspend_user(request: Request, user_id: int, current_user: dict = Depends(get_current_user), _: dict = Depends(require_admin)):
    db = request.app.state.db
    cursor = await db.execute("UPDATE users SET is_suspended = 1 WHERE id = ?", (user_id,))
    await db.commit()
    if cursor.rowcount == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return {"message": "User suspended"}


@router.put("/users/{user_id}/unsuspend")
async def unsuspend_user(request: Request, user_id: int, current_user: dict = Depends(get_current_user), _: dict = Depends(require_admin)):
    db = request.app.state.db
    cursor = await db.execute("UPDATE users SET is_suspended = 0 WHERE id = ?", (user_id,))
    await db.commit()
    if cursor.rowcount == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return {"message": "User unsuspended"}


@router.delete("/users/{user_id}")
async def delete_user(request: Request, user_id: int, current_user: dict = Depends(get_current_user), _: dict = Depends(require_admin)):
    db = request.app.state.db
    user = await db.execute("SELECT id FROM users WHERE id = ?", (user_id,))
    if await user.fetchone() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    await db.execute("DELETE FROM users WHERE id = ?", (user_id,))
    await db.commit()
    return {"message": "User removed successfully"}


@router.get("/questions/flagged")
async def list_flagged_questions(request: Request, current_user: dict = Depends(get_current_user), _: dict = Depends(require_admin)):
    db = request.app.state.db
    cursor = await db.execute(
        "SELECT id, user_id, title, description, type, difficulty, is_public, is_flagged, created_at FROM questions WHERE is_flagged = 1 ORDER BY created_at DESC"
    )
    rows = await cursor.fetchall()
    return [
        {
            "id": row[0],
            "user_id": row[1],
            "title": row[2],
            "description": row[3],
            "type": row[4],
            "difficulty": row[5],
            "is_public": bool(row[6]),
            "is_flagged": bool(row[7]),
            "created_at": row[8],
        }
        for row in rows
    ]


@router.get("/comments/flagged")
async def list_flagged_comments(request: Request, current_user: dict = Depends(get_current_user), _: dict = Depends(require_admin)):
    db = request.app.state.db
    cursor = await db.execute(
        "SELECT id, user_id, question_id, content, is_flagged, created_at FROM comments WHERE is_flagged = 1 ORDER BY created_at DESC"
    )
    rows = await cursor.fetchall()
    return [
        {
            "id": row[0],
            "user_id": row[1],
            "question_id": row[2],
            "content": row[3],
            "is_flagged": bool(row[4]),
            "created_at": row[5],
        }
        for row in rows
    ]


@router.put("/questions/{question_id}/unflag")
async def unflag_question(request: Request, question_id: int, current_user: dict = Depends(get_current_user), _: dict = Depends(require_admin)):
    db = request.app.state.db
    cursor = await db.execute("UPDATE questions SET is_flagged = 0 WHERE id = ?", (question_id,))
    await db.commit()
    if cursor.rowcount == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Question not found")
    return {"message": "Question unflagged"}


@router.put("/comments/{comment_id}/unflag")
async def unflag_comment(request: Request, comment_id: int, current_user: dict = Depends(get_current_user), _: dict = Depends(require_admin)):
    db = request.app.state.db
    cursor = await db.execute("UPDATE comments SET is_flagged = 0 WHERE id = ?", (comment_id,))
    await db.commit()
    if cursor.rowcount == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found")
    return {"message": "Comment unflagged"}


@router.post("/comments/{comment_id}/flag")
async def flag_comment_admin(request: Request, comment_id: int, current_user: dict = Depends(get_current_user), _: dict = Depends(require_admin)):
    db = request.app.state.db
    try:
        await db.execute("UPDATE comments SET is_flagged = 1 WHERE id = ?", (comment_id,))
        await db.commit()
    except Exception:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unable to flag comment")
    return {"message": "Comment flagged"}


@router.delete("/comments/{comment_id}")
async def delete_comment(request: Request, comment_id: int, current_user: dict = Depends(get_current_user), _: dict = Depends(require_admin)):
    db = request.app.state.db
    cursor = await db.execute("DELETE FROM comments WHERE id = ?", (comment_id,))
    await db.commit()
    if cursor.rowcount == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found")
    return {"message": "Comment deleted"}


@router.delete("/questions/{question_id}")
async def delete_question(request: Request, question_id: int, current_user: dict = Depends(get_current_user), _: dict = Depends(require_admin)):
    db = request.app.state.db
    cursor = await db.execute("DELETE FROM questions WHERE id = ?", (question_id,))
    await db.commit()
    if cursor.rowcount == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Question not found")
    return {"message": "Question deleted"}


@router.get("/exams")
async def list_exams(request: Request, current_user: dict = Depends(get_current_user), _: dict = Depends(require_admin)):
    db = request.app.state.db
    cursor = await db.execute(
        "SELECT id, user_id, title, description, duration_minutes, total_marks, is_public, randomize_order, created_at, updated_at FROM exams ORDER BY created_at DESC"
    )
    rows = await cursor.fetchall()
    return [
        {
            "id": row[0],
            "user_id": row[1],
            "title": row[2],
            "description": row[3],
            "duration_minutes": row[4],
            "total_marks": row[5],
            "is_public": bool(row[6]),
            "randomize_order": bool(row[7]),
            "created_at": row[8],
            "updated_at": row[9],
        }
        for row in rows
    ]


@router.post("/exams/generate")
async def generate_admin_exam(request: Request, current_user: dict = Depends(get_current_user), _: dict = Depends(require_admin)):
    db = request.app.state.db
    body = await request.json()
    topic = (body.get("topic") or "").strip()
    count = int(body.get("count", 5))
    difficulty = body.get("difficulty", "mixed")
    duration_minutes = int(body.get("duration", 30))

    if count < 1:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Question count must be at least 1")
    if duration_minutes < 5:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Duration must be at least 5 minutes")

    query = "SELECT id FROM questions WHERE is_public = 1 AND is_flagged = 0"
    params: list = []
    if difficulty != "mixed":
        query += " AND difficulty = ?"
        params.append(difficulty)
    if topic:
        query += " AND (title LIKE ? OR description LIKE ? OR type LIKE ? OR explanation LIKE ?)"
        search_value = f"%{topic}%"
        params.extend([search_value, search_value, search_value, search_value])
    query += " ORDER BY RANDOM() LIMIT ?"
    params.append(count)

    cursor = await db.execute(query, tuple(params))
    rows = await cursor.fetchall()
    if not rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No matching questions found for exam generation")

    questions = [
        {"question_id": row[0], "marks": 1, "question_order": idx + 1}
        for idx, row in enumerate(rows)
    ]
    title = f"Generated Exam: {topic or 'Mixed Topics'}"
    description = f"Auto-generated exam for {topic or 'mixed topics'} at {difficulty} difficulty."
    total_marks = sum(q["marks"] for q in questions)

    exam = await exam_model.create_exam(
        db,
        user_id=current_user["id"],
        title=title,
        description=description,
        duration_minutes=duration_minutes,
        total_marks=total_marks,
        is_public=True,
        randomize_order=False,
        randomize_options=False,
        secure_mode=False,
        questions=questions,
    )
    return exam


@router.get("/analytics/overview")
async def get_analytics_overview(request: Request, current_user: dict = Depends(get_current_user), _: dict = Depends(require_admin)):
    db = request.app.state.db
    
    active_users_cursor = await db.execute("SELECT COUNT(DISTINCT user_id) FROM exam_attempts WHERE submitted_at >= datetime('now', '-30 days')")
    active_users = (await active_users_cursor.fetchone())[0]
    
    questions_created_cursor = await db.execute("SELECT COUNT(*) FROM questions WHERE created_at >= datetime('now', '-30 days')")
    questions_created = (await questions_created_cursor.fetchone())[0]
    
    exams_taken_cursor = await db.execute("SELECT COUNT(*) FROM exam_attempts WHERE submitted_at >= datetime('now', '-30 days')")
    exams_taken = (await exams_taken_cursor.fetchone())[0]
    
    avg_score_cursor = await db.execute("SELECT AVG(CAST(score AS FLOAT) / NULLIF(total_marks, 0) * 100) FROM exam_attempts WHERE submitted_at >= datetime('now', '-30 days')")
    avg_score_row = await avg_score_cursor.fetchone()
    avg_score = float((avg_score_row[0] if avg_score_row else 0) or 0)
    
    return {
        "active_users_30d": active_users,
        "questions_created_30d": questions_created,
        "exams_taken_30d": exams_taken,
        "average_score_30d": round(avg_score, 2),
    }


@router.get("/analytics/content-moderation")
async def get_moderation_stats(request: Request, current_user: dict = Depends(get_current_user), _: dict = Depends(require_admin)):
    db = request.app.state.db
    
    flagged_questions = await db.execute("SELECT COUNT(*) FROM questions WHERE is_flagged = 1")
    flagged_comments = await db.execute("SELECT COUNT(*) FROM comments WHERE is_flagged = 1")
    total_questions = await db.execute("SELECT COUNT(*) FROM questions")
    total_comments = await db.execute("SELECT COUNT(*) FROM comments")
    
    return {
        "flagged_questions": (await flagged_questions.fetchone())[0],
        "total_questions": (await total_questions.fetchone())[0],
        "flagged_comments": (await flagged_comments.fetchone())[0],
        "total_comments": (await total_comments.fetchone())[0],
    }


@router.post("/moderate/batch")
async def moderate_batch(request: Request, current_user: dict = Depends(get_current_user), _: dict = Depends(require_admin)):
    db = request.app.state.db
    flagged = []

    comment_cursor = await db.execute("SELECT id, content FROM comments WHERE is_flagged = 0 ORDER BY created_at ASC")
    comment_rows = await comment_cursor.fetchall()
    for row in comment_rows:
        comment_id, content = row[0], row[1]
        verdict = await ai_service.moderation_filter(content)
        if verdict.get("is_toxic") or verdict.get("is_spam"):
            await db.execute("UPDATE comments SET is_flagged = 1 WHERE id = ?", (comment_id,))
            flagged.append({"type": "comment", "id": comment_id, "reason": verdict.get("reason")})

    question_cursor = await db.execute("SELECT id, title, description FROM questions WHERE is_flagged = 0 ORDER BY created_at ASC")
    question_rows = await question_cursor.fetchall()
    for row in question_rows:
        question_id, title, description = row[0], row[1], row[2]
        text = f"{title} {description or ''}".strip()
        verdict = await ai_service.moderation_filter(text)
        if verdict.get("is_toxic") or verdict.get("is_spam"):
            await db.execute("UPDATE questions SET is_flagged = 1 WHERE id = ?", (question_id,))
            flagged.append({"type": "question", "id": question_id, "reason": verdict.get("reason")})

    await db.commit()
    return {"flagged_count": len(flagged), "flagged_items": flagged}


@router.get("/approvals/pending")
async def list_pending_approvals(request: Request, current_user: dict = Depends(get_current_user), _: dict = Depends(require_admin)):
    """Get all pending content approvals."""
    db = request.app.state.db
    cursor = await db.execute(
        """SELECT id, content_type, content_id, submitted_by, status, admin_notes, created_at 
           FROM pending_approvals 
           WHERE status = 'pending'
           ORDER BY created_at ASC"""
    )
    rows = await cursor.fetchall()
    return [
        {
            "id": row[0],
            "content_type": row[1],
            "content_id": row[2],
            "submitted_by": row[3],
            "status": row[4],
            "admin_notes": row[5],
            "created_at": row[6],
        }
        for row in rows
    ]


@router.post("/approvals/{approval_id}/approve")
async def approve_content(request: Request, approval_id: int, current_user: dict = Depends(get_current_user), _: dict = Depends(require_admin)):
    """Approve pending content."""
    db = request.app.state.db
    body = await request.json()
    admin_notes = body.get("admin_notes", "")

    # Get approval record
    approval_cursor = await db.execute(
        "SELECT content_type, content_id FROM pending_approvals WHERE id = ?", (approval_id,)
    )
    approval = await approval_cursor.fetchone()
    if not approval:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Approval not found")

    content_type, content_id = approval[0], approval[1]

    # Update approval status
    await db.execute(
        "UPDATE pending_approvals SET status = 'approved', admin_id = ?, admin_notes = ?, reviewed_at = CURRENT_TIMESTAMP WHERE id = ?",
        (current_user["id"], admin_notes, approval_id),
    )

    # Update content status (publish if it was draft)
    if content_type == "question":
        await db.execute("UPDATE questions SET requires_approval = 0 WHERE id = ?", (content_id,))
    elif content_type == "exam":
        await db.execute("UPDATE exams SET requires_approval = 0 WHERE id = ?", (content_id,))

    await db.commit()
    return {"message": f"{content_type} approved successfully"}


@router.post("/approvals/{approval_id}/reject")
async def reject_content(request: Request, approval_id: int, current_user: dict = Depends(get_current_user), _: dict = Depends(require_admin)):
    """Reject pending content."""
    db = request.app.state.db
    body = await request.json()
    admin_notes = body.get("admin_notes", "")

    # Get approval record
    approval_cursor = await db.execute(
        "SELECT content_type, content_id FROM pending_approvals WHERE id = ?", (approval_id,)
    )
    approval = await approval_cursor.fetchone()
    if not approval:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Approval not found")

    content_type, content_id = approval[0], approval[1]

    # Update approval status
    await db.execute(
        "UPDATE pending_approvals SET status = 'rejected', admin_id = ?, admin_notes = ?, reviewed_at = CURRENT_TIMESTAMP WHERE id = ?",
        (current_user["id"], admin_notes, approval_id),
    )

    # Delete rejected content or mark as archived
    if content_type == "question":
        await db.execute("DELETE FROM questions WHERE id = ?", (content_id,))
    elif content_type == "exam":
        await db.execute("DELETE FROM exams WHERE id = ?", (content_id,))

    await db.commit()
    return {"message": f"{content_type} rejected and deleted"}
