from fastapi import Depends, HTTPException, Request, status

try:
    from backend.services.auth_service import decode_token
    from backend.models.user_model import get_user_by_id
except ImportError:
    from services.auth_service import decode_token
    from models.user_model import get_user_by_id


async def get_current_user(request: Request) -> dict:
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing or invalid authorization header")

    token = auth_header.split(" ", 1)[1].strip()
    try:
        payload = decode_token(token)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")

    user_id = int(payload["sub"])
    db = request.app.state.db
    user = await get_user_by_id(db, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    if user.get("is_suspended"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account suspended")
    return user


async def get_current_user_optional(request: Request) -> dict | None:
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.lower().startswith("bearer "):
        return None

    token = auth_header.split(" ", 1)[1].strip()
    try:
        payload = decode_token(token)
    except ValueError:
        return None

    user_id = int(payload["sub"])
    db = request.app.state.db
    user = await get_user_by_id(db, user_id)
    if user is None or user.get("is_suspended"):
        return None
    return user
