from fastapi import APIRouter, Depends, HTTPException, Request, status

try:
    from backend.schemas.exam_schema import ExamCreate, ExamOut, ExamUpdate, AttemptStart, AttemptSave, AttemptSubmit, ResultOut, UpcomingExamOut
    from backend.services.exam_service import start_exam_attempt, submit_exam_attempt, save_exam_attempt_progress, notify_new_exam
    from backend.services import leaderboard_service, exam_generator
    from backend.models import exam_model
    from backend.middlewares.auth import get_current_user, get_current_user_optional
    from backend.middlewares.role import require_admin
except ImportError:
    from schemas.exam_schema import ExamCreate, ExamOut, ExamUpdate, AttemptStart, AttemptSave, AttemptSubmit, ResultOut, UpcomingExamOut
    from services.exam_service import start_exam_attempt, submit_exam_attempt, save_exam_attempt_progress, notify_new_exam
    from services import leaderboard_service, exam_generator
    from models import exam_model
    from middlewares.auth import get_current_user, get_current_user_optional
    from middlewares.role import require_admin

router = APIRouter(prefix="/api/v1/exams", tags=["exams"])


@router.get("/", response_model=list[ExamOut])
async def read_exams(request: Request, page: int = 1, limit: int = 20):
    db = request.app.state.db
    return await exam_model.list_exams(db, page=page, limit=limit)


@router.get("/upcoming", response_model=list[UpcomingExamOut])
async def read_upcoming_exams(request: Request, page: int = 1, limit: int = 20):
    """Get upcoming scheduled exams with dates and deadlines."""
    db = request.app.state.db
    offset = (page - 1) * limit
    return await exam_model.get_upcoming_exams(db, limit=limit, offset=offset)


@router.get("/export")
async def export_exams(request: Request, current_user: dict = Depends(get_current_user)):
    db = request.app.state.db
    exams = await exam_model.list_exams(db, page=1, limit=1000, only_public=False)
    return {"exams": exams}


@router.post("/import", response_model=list[ExamOut])
async def import_exams(request: Request, payload: dict, current_user: dict = Depends(get_current_user)):
    db = request.app.state.db
    if current_user["role"] != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only admins can import exams")
    imported = []
    for item in payload.get("exams", []):
        exam = await exam_model.create_exam(
            db,
            user_id=current_user["id"],
            title=item["title"],
            description=item.get("description"),
            duration_minutes=item["duration_minutes"],
            total_marks=item["total_marks"],
            is_public=item.get("is_public", False),
            randomize_order=item.get("randomize_order", False),
            randomize_options=item.get("randomize_options", False),
            secure_mode=item.get("secure_mode", False),
            questions=item.get("questions", []),
        )
        imported.append(exam)
    return imported


@router.get("/{exam_id}", response_model=ExamOut)
async def read_exam(request: Request, exam_id: int, current_user: dict | None = Depends(get_current_user_optional)):
    db = request.app.state.db
    exam = await exam_model.get_exam_by_id(db, exam_id, current_user_id=current_user and current_user.get("id"))
    if exam is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Exam not found")
    if exam["secure_mode"] and (current_user is None or (current_user["role"] != "admin" and current_user["id"] != exam["user_id"])):
        exam = {**exam, "questions": []}
    return exam


@router.get("/{exam_id}/attempt/latest", response_model=AttemptStart)
async def read_latest_attempt(request: Request, exam_id: int, current_user: dict = Depends(get_current_user)):
    db = request.app.state.db
    attempt = await exam_model.get_latest_active_attempt(db, exam_id, current_user["id"])
    if attempt is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No active attempt found")
    exam = await exam_model.get_exam_by_id(db, exam_id)
    if exam is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Exam not found")
    attempt["questions"] = attempt.get("question_order") or exam["questions"]
    return attempt


@router.patch("/attempt/{attempt_id}", response_model=AttemptStart)
async def save_attempt(request: Request, attempt_id: int, payload: AttemptSave, current_user: dict = Depends(get_current_user)):
    db = request.app.state.db
    attempt = await save_exam_attempt_progress(
        db,
        attempt_id,
        current_user["id"],
        payload.time_taken_seconds,
        {str(k): str(v) for k, v in payload.answers.items()},
    )
    if attempt is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attempt not found or cannot be saved")
    exam = await exam_model.get_exam_by_id(db, attempt["exam_id"])
    if exam is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Exam not found")
    attempt["questions"] = attempt.get("question_order") or exam["questions"]
    return attempt


@router.patch("/{exam_id}/schedule", response_model=ExamOut)
async def schedule_exam(request: Request, exam_id: int, payload: dict, current_user: dict = Depends(get_current_user)):
    """Schedule an exam with a specific date and deadline (admin or exam creator only)."""
    db = request.app.state.db
    exam = await exam_model.get_exam_by_id(db, exam_id)
    if exam is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Exam not found")
    if current_user["role"] != "admin" and exam["user_id"] != current_user["id"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to schedule this exam")
    
    updated = await exam_model.update_exam(
        db,
        exam_id,
        scheduled_at=payload.get("scheduled_at"),
        deadline=payload.get("deadline"),
    )
    if updated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Exam not found")
    return updated


@router.post("/", response_model=ExamOut, status_code=status.HTTP_201_CREATED)
async def create_exam(request: Request, payload: ExamCreate, current_user: dict = Depends(get_current_user)):
    db = request.app.state.db
    exam = await exam_model.create_exam(
        db,
        user_id=current_user["id"],
        title=payload.title,
        description=payload.description,
        duration_minutes=payload.duration_minutes,
        total_marks=payload.total_marks,
        is_public=payload.is_public,
        randomize_order=payload.randomize_order,
        randomize_options=payload.randomize_options,
        secure_mode=payload.secure_mode,
        questions=[question.model_dump() for question in payload.questions],
        requires_approval=current_user["role"] != "admin",
        scheduled_at=payload.scheduled_at,
        deadline=payload.deadline,
    )
    if not exam.get("requires_approval", False):
        await notify_new_exam(db, exam)
    return exam


@router.put("/{exam_id}", response_model=ExamOut)
async def update_exam(request: Request, exam_id: int, payload: ExamUpdate, current_user: dict = Depends(get_current_user)):
    db = request.app.state.db
    exam = await exam_model.get_exam_by_id(db, exam_id)
    if exam is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Exam not found")
    if current_user["role"] != "admin" and exam["user_id"] != current_user["id"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to update this exam")
    updated = await exam_model.update_exam(
        db,
        exam_id,
        title=payload.title,
        description=payload.description,
        duration_minutes=payload.duration_minutes,
        total_marks=payload.total_marks,
        is_public=payload.is_public,
        randomize_order=payload.randomize_order,
        randomize_options=payload.randomize_options,
        secure_mode=payload.secure_mode,
        questions=[question.model_dump() for question in payload.questions] if payload.questions is not None else None,
        scheduled_at=payload.scheduled_at,
        deadline=payload.deadline,
    )
    if updated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Exam not found")
    return updated


@router.delete("/{exam_id}")
async def delete_exam(request: Request, exam_id: int, current_user: dict = Depends(get_current_user)):
    db = request.app.state.db
    exam = await exam_model.get_exam_by_id(db, exam_id)
    if exam is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Exam not found")
    if current_user["role"] != "admin" and exam["user_id"] != current_user["id"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to delete this exam")
    await exam_model.delete_exam(db, exam_id)
    return {"message": "Exam deleted successfully"}


@router.post("/{exam_id}/start", response_model=AttemptStart)
async def start_exam(request: Request, exam_id: int, current_user: dict = Depends(get_current_user)):
    db = request.app.state.db
    attempt = await start_exam_attempt(db, exam_id, current_user["id"])
    exam = await exam_model.get_exam_by_id(db, exam_id)
    if exam is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Exam not found")
    attempt["questions"] = attempt.get("question_order") or exam["questions"]
    return attempt


@router.post("/{exam_id}/submit", response_model=ResultOut)
async def submit_exam(request: Request, exam_id: int, payload: AttemptSubmit, current_user: dict = Depends(get_current_user)):
    db = request.app.state.db
    attempt = await exam_model.get_attempt(db, payload.attempt_id)
    if attempt is None or attempt["exam_id"] != exam_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attempt not found")
    submitted = await submit_exam_attempt(db, payload.attempt_id, current_user["id"], payload.time_taken_seconds, payload.answers)
    submitted["questions"] = submitted.get("question_order") or []
    return submitted


@router.get("/{exam_id}/result/{attempt_id}", response_model=ResultOut)
async def read_exam_result(request: Request, exam_id: int, attempt_id: int, current_user: dict = Depends(get_current_user)):
    db = request.app.state.db
    attempt = await exam_model.get_attempt(db, attempt_id)
    if attempt is None or attempt["exam_id"] != exam_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attempt not found")
    if current_user["role"] != "admin" and attempt["user_id"] != current_user["id"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to view this attempt")
    attempt["questions"] = attempt.get("question_order") or []
    return attempt


@router.get("/{exam_id}/leaderboard")
async def read_exam_leaderboard(request: Request, exam_id: int):
    db = request.app.state.db
    return await leaderboard_service.get_exam_leaderboard(db, exam_id)


@router.post("/generate", response_model=ExamOut)
async def generate_exam(request: Request, payload: ExamCreate, current_user: dict = Depends(get_current_user), _: dict = Depends(require_admin)):
    db = request.app.state.db
    exam = await exam_generator.generate_exam(
        db,
        user_id=current_user["id"],
        title=payload.title,
        description=payload.description,
        duration_minutes=payload.duration_minutes,
        total_marks=payload.total_marks,
        is_public=payload.is_public,
        randomize_order=payload.randomize_order,
        randomize_options=payload.randomize_options,
        secure_mode=payload.secure_mode,
        questions=[question.model_dump() for question in payload.questions],
    )
    await notify_new_exam(db, exam)
    return exam
