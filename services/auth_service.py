from datetime import datetime, timedelta

from jose import JWTError, jwt
from passlib.context import CryptContext

try:
    from backend.config import settings
    from backend.models.user_model import create_user, get_user_by_email
except ImportError:
    from config import settings
    from models.user_model import create_user, get_user_by_email

pwd_context = CryptContext(
    schemes=["bcrypt_sha256"],
    deprecated="auto"
)

ACCESS_TOKEN_EXPIRE_MINUTES = 24 * 60
ADMIN_TOKEN_EXPIRE_MINUTES = 8 * 60


def _create_access_token(data: dict, expires_delta: timedelta) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + expires_delta
    to_encode.update({"exp": expire})

    return jwt.encode(
        to_encode,
        settings.SECRET_KEY,
        algorithm="HS256"
    )


async def register_user(
    db,
    name: str,
    email: str,
    password: str,
    role: str = "student"
) -> dict:

    existing = await get_user_by_email(db, email)

    if existing is not None:
        raise ValueError("Email already registered")

    password_hash = pwd_context.hash(password)

    return await create_user(
        db,
        name=name,
        email=email,
        password_hash=password_hash,
        role=role
    )


async def login_user(
    db,
    email: str,
    password: str,
    is_admin: bool = False
) -> dict:

    user = await get_user_by_email(db, email)

    if user is None or not pwd_context.verify(password, user["password_hash"]):
        raise ValueError("Invalid credentials")

    if user.get("is_suspended"):
        raise PermissionError("Account suspended")

    if is_admin and user["role"] != "admin":
        raise PermissionError("Admin login required")

    return user


def create_token_for_user(user: dict, is_admin: bool = False) -> str:
    expires = timedelta(
        minutes=ADMIN_TOKEN_EXPIRE_MINUTES if is_admin else ACCESS_TOKEN_EXPIRE_MINUTES
    )

    payload = {
        "sub": str(user["id"]),
        "role": user["role"]
    }

    return _create_access_token(payload, expires)


def decode_token(token: str) -> dict:
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=["HS256"]
        )

        if "sub" not in payload or "role" not in payload:
            raise JWTError("Invalid token payload")

        return payload

    except JWTError as exc:
        raise ValueError("Could not validate token") from exc