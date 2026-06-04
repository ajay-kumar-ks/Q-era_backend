"""
Search router for full-text search endpoints.
Provides keyword search on questions and exams with optional semantic fallback.
"""

from fastapi import APIRouter, Request, Query, HTTPException

try:
    from backend.middlewares.auth import get_current_user
    from backend.models.search_model import keyword_search_questions, keyword_search_exams
    from backend.services.ai_service import semantic_search
except ImportError:
    from middlewares.auth import get_current_user
    from models.search_model import keyword_search_questions, keyword_search_exams
    from services.ai_service import semantic_search

router = APIRouter(prefix="/api/v1/search", tags=["search"])


@router.get("/questions")
async def search_questions(
    request: Request,
    q: str = Query(..., min_length=1, description="Search query"),
    tags: str | None = Query(None, description="Comma-separated tag names"),
    difficulty: str | None = Query(None, pattern="^(easy|medium|hard)$"),
    type: str | None = Query(None, pattern="^(mcq|true_false|short_answer|descriptive)$"),
    mode: str = Query("keyword", pattern="^(keyword|semantic)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50),
):
    """
    Search questions by keyword or semantic similarity.
    
    Query Parameters:
    - q: Search query (required)
    - tags: Comma-separated tag names (optional)
    - difficulty: Filter by difficulty (easy, medium, hard) (optional)
    - type: Filter by question type (mcq, true_false, short_answer, descriptive) (optional)
    - mode: Search mode - keyword (FTS5) or semantic (AI fallback) (default: keyword)
    - page: Page number (1-indexed, default: 1)
    - page_size: Results per page (1-50, default: 10)
    
    Returns:
    {
        "results": [question_objects],
        "total": total_count,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
        "search_mode": "keyword" or "semantic"
    }
    """
    db = request.app.state.db
    
    # Parse tags
    tag_list = None
    if tags:
        tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    
    # Keyword search
    result = await keyword_search_questions(
        db,
        query=q,
        tags=tag_list,
        difficulty=difficulty,
        question_type=type,
        page=page,
        page_size=page_size,
    )
    
    # Semantic fallback: if mode is semantic or keyword returns < 3 results
    if mode == "semantic" or (result["total"] < 3 and mode == "keyword"):
        semantic_results = await semantic_search(q)
        if semantic_results:
            result["results"] = semantic_results
            result["search_mode"] = "semantic"
        else:
            result["search_mode"] = "keyword"
    else:
        result["search_mode"] = "keyword"
    
    return result


@router.get("/exams")
async def search_exams(
    request: Request,
    q: str = Query(..., min_length=1, description="Search query"),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50),
):
    """
    Search exams by keyword on title and description.
    
    Query Parameters:
    - q: Search query (required)
    - page: Page number (1-indexed, default: 1)
    - page_size: Results per page (1-50, default: 10)
    
    Returns:
    {
        "results": [exam_objects],
        "total": total_count,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages
    }
    """
    db = request.app.state.db
    
    result = await keyword_search_exams(
        db,
        query=q,
        page=page,
        page_size=page_size,
    )
    
    return result
