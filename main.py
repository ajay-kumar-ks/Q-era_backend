from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

try:
    from backend.config import settings
    from backend.database import init_db, close_db
    from backend.middlewares.rate_limit import limiter
    from backend.routers.auth_router import router as auth_router
    from backend.routers.health import router as health_router
    from backend.routers.question_router import router as question_router
    from backend.routers.comment_router import router as comment_router
    from backend.routers.exam_router import router as exam_router
    from backend.routers.leaderboard_router import router as leaderboard_router
    from backend.routers.user_router import router as user_router
    from backend.routers.notification_router import router as notification_router
    from backend.routers.admin_router import router as admin_router
    from backend.routers.search_router import router as search_router
    from backend.routers.review_router import router as review_router
    from backend.routers.import_export_router import router as import_export_router
except ImportError:
    from config import settings
    from database import init_db, close_db
    from middlewares.rate_limit import limiter
    from routers.auth_router import router as auth_router
    from routers.health import router as health_router
    from routers.question_router import router as question_router
    from routers.comment_router import router as comment_router
    from routers.exam_router import router as exam_router
    from routers.leaderboard_router import router as leaderboard_router
    from routers.user_router import router as user_router
    from routers.notification_router import router as notification_router
    from routers.admin_router import router as admin_router
    from routers.search_router import router as search_router
    from routers.review_router import router as review_router
    from routers.import_export_router import router as import_export_router

from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

app = FastAPI(title="QERA Backend", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)

def _rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )

app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

@app.on_event("startup")
async def startup_event():
    await init_db(app)

@app.on_event("shutdown")
async def shutdown_event():
    await close_db(app)

app.include_router(health_router)
app.include_router(auth_router)
app.include_router(question_router)
app.include_router(comment_router)
app.include_router(exam_router)
app.include_router(leaderboard_router)
app.include_router(user_router)
app.include_router(notification_router)
app.include_router(admin_router)
app.include_router(search_router)
app.include_router(review_router)
app.include_router(import_export_router)
