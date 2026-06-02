from fastapi import APIRouter, Depends, HTTPException, Request, status

try:
    from backend.schemas.auth_schema import LoginRequest, RegisterRequest, TokenOut, UserOut
    from backend.services.auth_service import create_token_for_user, login_user, register_user
    from backend.middlewares.auth import get_current_user
    from backend.middlewares.rate_limit import limiter
except ImportError:
    from schemas.auth_schema import LoginRequest, RegisterRequest, TokenOut, UserOut
    from services.auth_service import create_token_for_user, login_user, register_user
    from middlewares.auth import get_current_user
    from middlewares.rate_limit import limiter

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/register", response_model=UserOut)
@limiter.limit("10/minute")
async def register(request: Request, payload: RegisterRequest):
    db = request.app.state.db
    try:
        user = await register_user(db, payload.name, payload.email, payload.password)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    return UserOut(**user)


@router.post("/login", response_model=TokenOut)
@limiter.limit("10/minute")
async def login(request: Request, payload: LoginRequest):
    db = request.app.state.db
    try:
        user = await login_user(db, payload.email, payload.password)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    token = create_token_for_user(user)
    return TokenOut(access_token=token, user=UserOut(**user))


@router.post("/admin/login", response_model=TokenOut)
@limiter.limit("10/minute")
async def admin_login(request: Request, payload: LoginRequest):
    db = request.app.state.db
    try:
        user = await login_user(db, payload.email, payload.password, is_admin=True)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    token = create_token_for_user(user, is_admin=True)
    return TokenOut(access_token=token, user=UserOut(**user))


@router.get("/me", response_model=UserOut)
async def me(current_user: dict = Depends(get_current_user)):
    return UserOut(**current_user)


@router.post("/logout")
async def logout(current_user: dict = Depends(get_current_user)):
    return {"message": "Successfully logged out"}
