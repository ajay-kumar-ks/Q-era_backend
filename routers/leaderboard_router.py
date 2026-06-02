from fastapi import APIRouter, Request

try:
    from backend.services.leaderboard_service import get_global_leaderboard, get_exam_leaderboard
except ImportError:
    from services.leaderboard_service import get_global_leaderboard, get_exam_leaderboard

router = APIRouter(prefix="/api/v1/leaderboard", tags=["leaderboard"])


@router.get("/global")
async def read_global_leaderboard(request: Request):
    db = request.app.state.db
    return await get_global_leaderboard(db)


@router.get("/exam/{exam_id}")
async def read_exam_leaderboard(request: Request, exam_id: int):
    db = request.app.state.db
    return await get_exam_leaderboard(db, exam_id)
