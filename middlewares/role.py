from fastapi import Depends, HTTPException, status

try:
    from backend.middlewares.auth import get_current_user
except ImportError:
    from middlewares.auth import get_current_user


async def require_admin(current_user: dict = Depends(get_current_user)) -> dict:
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin privileges required")
    return current_user
