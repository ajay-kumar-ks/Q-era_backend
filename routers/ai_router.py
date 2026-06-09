"""
AI features router — dedicated endpoints for Gemini-powered AI capabilities.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status

try:
    from backend.middlewares.auth import get_current_user, get_current_user_optional
    from backend.middlewares.role import require_admin
    from backend.schemas.ai_schema import (
        DuplicateCheckRequest,
        DuplicateCheckResponse,
        TagSuggestionRequest,
        TagSuggestionResponse,
        DifficultyAnalysisRequest,
        DifficultyAnalysisResponse,
        ModerationRequest,
        ModerationResponse,
        AIHealthResponse,
        GenerateQuestionsRequest,
        GenerateQuestionsResponse,
        GeneratedQuestionOut,
        GeneratedOptionOut,
        RequestAIQuestionsRequest,
        RequestAIQuestionsResponse,
        GenerateExamRequest,
        GenerateExamResponse,
        GenerateExamQuestionOut,
        ExplainRequest,
        ExplainResponse,
    )
    from backend.services import ai_service
    from backend.services.notification_service import create_notification
    from backend.models.question_model import create_question as db_create_question
    from backend.models.exam_model import create_exam as db_create_exam
    from backend.config import get_api_key_manager, settings
except ImportError:
    from middlewares.auth import get_current_user, get_current_user_optional
    from middlewares.role import require_admin
    from schemas.ai_schema import (
        DuplicateCheckRequest,
        DuplicateCheckResponse,
        TagSuggestionRequest,
        TagSuggestionResponse,
        DifficultyAnalysisRequest,
        DifficultyAnalysisResponse,
        ModerationRequest,
        ModerationResponse,
        AIHealthResponse,
        GenerateQuestionsRequest,
        GenerateQuestionsResponse,
        GeneratedQuestionOut,
        GeneratedOptionOut,
        RequestAIQuestionsRequest,
        RequestAIQuestionsResponse,
        GenerateExamRequest,
        GenerateExamResponse,
        GenerateExamQuestionOut,
        ExplainRequest,
        ExplainResponse,
    )
    from services import ai_service
    from services.notification_service import create_notification
    from models.question_model import create_question as db_create_question
    from models.exam_model import create_exam as db_create_exam
    from config import get_api_key_manager, settings

router = APIRouter(prefix="/api/v1/ai", tags=["ai"])


@router.get("/health", response_model=AIHealthResponse)
async def ai_health():
    """Health check — reports AI service status and key configuration."""
    key_manager = get_api_key_manager()
    keys_count = len(key_manager.active_keys)
    gemini_available = keys_count > 0
    return AIHealthResponse(
        status="operational" if gemini_available else "no_keys_configured",
        keys_configured=keys_count,
        gemini_available=gemini_available,
        model="gemini-2.0-flash",
    )


@router.post("/duplicate-check", response_model=DuplicateCheckResponse)
@router.post("/check-duplicate", response_model=DuplicateCheckResponse, include_in_schema=False)
async def check_duplicate(body: DuplicateCheckRequest, request: Request):
    """Check if a question is likely a duplicate using AI."""
    db_conn = getattr(request.app.state, "db", None)
    result = await ai_service.check_duplicate(db_conn, body.title, body.description)
    return DuplicateCheckResponse(
        is_duplicate=result["is_duplicate"],
        confidence=result["confidence"],
        reason=result.get("reason", ""),
        similar_ids=result.get("similar_ids", []),
    )


@router.post("/suggest-tags", response_model=TagSuggestionResponse)
async def suggest_tags(body: TagSuggestionRequest):
    """Suggest tags for a question using AI."""
    tags = await ai_service.suggest_tags(None, body.title, body.description)
    return TagSuggestionResponse(tags=tags)


@router.post("/analyze-difficulty", response_model=DifficultyAnalysisResponse)
async def analyze_difficulty(body: DifficultyAnalysisRequest):
    """Analyze and suggest difficulty level for a question."""
    result = await ai_service.analyze_difficulty(None, body.title, body.description)
    return DifficultyAnalysisResponse(
        difficulty=result["difficulty"],
        confidence=result["confidence"],
    )


@router.post("/moderate", response_model=ModerationResponse)
async def moderate_content(body: ModerationRequest):
    """Check text content for toxicity, spam, or policy violations."""
    result = await ai_service.moderation_filter(body.text)
    return ModerationResponse(
        is_toxic=result["is_toxic"],
        is_spam=result["is_spam"],
        reason=result.get("reason"),
    )


# ---------------------------------------------------------------------------
# Phase 2.1 — AI Question Generation (admin only)
# ---------------------------------------------------------------------------

@router.post(
    "/generate-questions",
    response_model=GenerateQuestionsResponse,
    status_code=status.HTTP_201_CREATED,
)
async def generate_questions(
    body: GenerateQuestionsRequest,
    request: Request,
    current_user: dict = Depends(get_current_user),
    _admin: dict = Depends(require_admin),
):
    """
    Admin-only: Generate questions with AI and save them directly to the DB.
    Returns the created questions.
    """
    db = request.app.state.db

    # Generate via Gemini
    try:
        generated = await ai_service.generate_questions(
            topic=body.topic,
            q_type=body.type,
            difficulty=body.difficulty,
            count=body.count,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))

    # Save each question to DB
    created_questions = []
    for q in generated:
        try:
            saved = await db_create_question(
                db,
                user_id=current_user["id"],
                title=q["title"],
                description=q.get("description"),
                type=q["type"],
                correct_answer=q["correct_answer"],
                difficulty=q["difficulty"],
                explanation=q.get("explanation"),
                image_url=None,
                media_url=None,
                attachment_url=None,
                is_public=body.is_public,
                tag_names=q["tags"],
                options=q["options"],
                requires_approval=False,  # Admin-generated, auto-approved
            )
            if saved:
                out_options = [
                    GeneratedOptionOut(
                        option_text=o["option_text"],
                        option_order=o["option_order"],
                    )
                    for o in (saved.get("options") or [])
                ]
                created_questions.append(
                    GeneratedQuestionOut(
                        id=saved["id"],
                        title=saved["title"],
                        description=saved.get("description"),
                        type=saved["type"],
                        correct_answer=saved["correct_answer"],
                        difficulty=saved["difficulty"],
                        explanation=saved.get("explanation"),
                        tags=[t["name"] for t in (saved.get("tags") or [])],
                        options=out_options,
                    )
                )
        except Exception as exc:
            # Log and continue — don't fail the whole batch for one bad question
            import logging as _log
            _log.getLogger("ai_router").warning("Failed to save generated question: %s", exc)

    if not created_questions:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="AI generated questions but none could be saved. Check server logs.",
        )

    return GenerateQuestionsResponse(
        created=len(created_questions),
        questions=created_questions,
    )


# ---------------------------------------------------------------------------
# Phase 2.1 — User Request for AI Questions
# ---------------------------------------------------------------------------

@router.post("/request-questions", response_model=RequestAIQuestionsResponse)
async def request_ai_questions(
    body: RequestAIQuestionsRequest,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """
    Any logged-in user can request that an admin generates questions on a topic.
    Sends a notification to all admins.
    """
    db = request.app.state.db

    # Compose message for admin notification
    note_part = f' Note: "{body.note}"' if body.note else ""
    message = (
        f'User "{current_user.get("name", current_user["id"])}" requests {body.count} '
        f'{body.difficulty} {body.type} question(s) on "{body.topic}".{note_part}'
    )

    # Find all admins and notify them
    try:
        cursor = await db.execute("SELECT id FROM users WHERE role = 'admin'")
        admin_rows = await cursor.fetchall()
        for row in admin_rows:
            await create_notification(
                db,
                user_id=row[0],
                type="ai_question_request",
                message=message,
                reference_id=current_user["id"],
                reference_type="user",
            )
    except Exception as exc:
        import logging as _log
        _log.getLogger("ai_router").warning("Could not notify admins of question request: %s", exc)

    return RequestAIQuestionsResponse(
        message="Your request has been sent to the admins. They will generate questions on your topic soon.",
    )


# ---------------------------------------------------------------------------
# Phase 2.2 — AI Exam Generation (admin only)
# ---------------------------------------------------------------------------

@router.post(
    "/generate-exam",
    response_model=GenerateExamResponse,
    status_code=status.HTTP_201_CREATED,
)
async def generate_exam(
    body: GenerateExamRequest,
    request: Request,
    current_user: dict = Depends(get_current_user),
    _admin: dict = Depends(require_admin),
):
    """
    Admin-only: Generate a complete exam with AI — questions are created and
    saved to the DB, then assembled into a new exam record.
    """
    import logging as _log
    _logger = _log.getLogger("ai_router")
    db = request.app.state.db

    # 1. Generate exam spec from Gemini
    try:
        exam_spec = await ai_service.generate_exam(
            topic=body.topic,
            difficulty_mix={
                "easy": body.difficulty_mix.easy,
                "medium": body.difficulty_mix.medium,
                "hard": body.difficulty_mix.hard,
            },
            types=body.types,
            question_count=body.question_count,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))

    # 2. Save each question to DB
    saved_question_refs = []
    for idx, q in enumerate(exam_spec["questions"], start=1):
        try:
            saved = await db_create_question(
                db,
                user_id=current_user["id"],
                title=q["title"],
                description=q.get("description"),
                type=q["type"],
                correct_answer=q["correct_answer"],
                difficulty=q["difficulty"],
                explanation=q.get("explanation"),
                image_url=None,
                media_url=None,
                attachment_url=None,
                is_public=body.is_public,
                tag_names=q["tags"],
                options=q["options"],
                requires_approval=False,
            )
            if saved:
                saved_question_refs.append({
                    "question_id": saved["id"],
                    "marks": 1,
                    "question_order": idx,
                })
        except Exception as exc:
            _logger.warning("Failed to save generated exam question: %s", exc)

    if not saved_question_refs:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="AI generated questions but none could be saved. Check server logs.",
        )

    # 3. Create the exam with all saved questions
    total_marks = len(saved_question_refs)
    try:
        exam = await db_create_exam(
            db,
            user_id=current_user["id"],
            title=exam_spec["title"],
            description=exam_spec.get("description"),
            duration_minutes=body.duration_minutes,
            total_marks=total_marks,
            is_public=body.is_public,
            randomize_order=body.randomize_order,
            randomize_options=False,
            secure_mode=False,
            questions=saved_question_refs,
            requires_approval=False,
        )
    except Exception as exc:
        _logger.exception("Failed to create exam record: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Questions were saved but exam record creation failed. Check server logs.",
        )

    out_questions = [
        GenerateExamQuestionOut(
            question_id=q["question_id"],
            title=q["title"],
            type=q["type"],
            difficulty=q["difficulty"],
            marks=q["marks"],
            question_order=q["question_order"],
        )
        for q in (exam.get("questions") or [])
    ]

    return GenerateExamResponse(
        id=exam["id"],
        title=exam["title"],
        description=exam.get("description"),
        duration_minutes=exam["duration_minutes"],
        total_marks=exam["total_marks"],
        is_public=exam["is_public"],
        question_count=len(out_questions),
        questions=out_questions,
    )


@router.post("/reload-keys")
async def reload_api_keys():
    """Admin helper — reload API keys from .env without restarting the server."""
    try:
        from backend.config import reload_api_keys
    except ImportError:
        from config import reload_api_keys
    reload_api_keys()
    key_manager = get_api_key_manager()
    return {
        "status": "reloaded",
        "keys_configured": len(key_manager.active_keys),
    }


# ---------------------------------------------------------------------------
# Phase 2.3 — AI Answer Explanation
# ---------------------------------------------------------------------------

@router.post("/explain", response_model=ExplainResponse)
async def explain_answer(
    body: ExplainRequest,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """
    Explain why an answer is correct or incorrect for a given question.
    Available to all logged-in users.
    """
    db = request.app.state.db

    # Fetch the question from DB to get title, description and correct_answer
    try:
        from backend.models.question_model import get_question_by_id
    except ImportError:
        from models.question_model import get_question_by_id

    question = await get_question_by_id(db, body.question_id, current_user_id=current_user["id"])
    if question is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Question not found")

    result = await ai_service.explain_answer(
        question_title=question["title"],
        question_description=question.get("description"),
        correct_answer=question.get("correct_answer") or "",
        user_answer=body.user_answer,
        is_correct=body.is_correct,
    )

    return ExplainResponse(
        explanation=result["explanation"],
        key_concept=result.get("key_concept"),
        suggestion=result.get("suggestion"),
    )
