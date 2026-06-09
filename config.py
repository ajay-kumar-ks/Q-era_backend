import os
import threading
import time
from pydantic import Field, field_validator, ConfigDict, AliasChoices
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = ConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    SECRET_KEY: str = Field("changeme", validation_alias=AliasChoices("SECRET_KEY", "secret_key"))
    DB_PATH: str = Field("database_files/qera.db", validation_alias=AliasChoices("DB_PATH", "db_path"))
    DATABASE_URL: str | None = Field(None, validation_alias=AliasChoices("DATABASE_URL", "database_url"))
    ALLOWED_ORIGINS_STR: str = Field(
        default="http://localhost:5173",
        validation_alias=AliasChoices("ALLOWED_ORIGINS", "allowed_origins"),
    )
    DEBUG: bool = Field(True, validation_alias=AliasChoices("DEBUG", "debug"))
    CLOUDINARY_URL: str | None = Field(None, validation_alias=AliasChoices("CLOUDINARY_URL", "cloudinary_url"))
    CLOUDINARY_CLOUD_NAME: str | None = Field(None, validation_alias=AliasChoices("CLOUDINARY_CLOUD_NAME", "cloudinary_cloud_name"))
    CLOUDINARY_API_KEY: str | None = Field(None, validation_alias=AliasChoices("CLOUDINARY_API_KEY", "cloudinary_api_key"))
    CLOUDINARY_API_SECRET: str | None = Field(None, validation_alias=AliasChoices("CLOUDINARY_API_SECRET", "cloudinary_api_secret"))
    CLOUDINARY_UPLOAD_FOLDER: str | None = Field("questions", validation_alias=AliasChoices("CLOUDINARY_UPLOAD_FOLDER", "cloudinary_upload_folder"))
    GOOGLE_AI_STUDIO_API_KEYS: str = Field("", validation_alias=AliasChoices("GOOGLE_AI_STUDIO_API_KEYS", "google_ai_studio_api_keys"))

    @field_validator("DEBUG", mode="before")
    @classmethod
    def parse_debug(cls, v):
        if isinstance(v, str):
            normalized = v.strip().lower()
            if normalized in {"release", "prod", "production"}:
                return False
            if normalized in {"debug", "dev", "development"}:
                return True
        return v

    @property
    def ALLOWED_ORIGINS(self) -> list[str]:
        """Parse ALLOWED_ORIGINS_STR into a list."""
        if not self.ALLOWED_ORIGINS_STR or self.ALLOWED_ORIGINS_STR == "":
            return ["http://localhost:5173"]
        return [origin.strip() for origin in self.ALLOWED_ORIGINS_STR.split(",") if origin.strip()]

    @property
    def ai_api_keys(self) -> list[str]:
        """Return parsed, non-empty API keys."""
        if not self.GOOGLE_AI_STUDIO_API_KEYS:
            return []
        return [k.strip() for k in self.GOOGLE_AI_STUDIO_API_KEYS.split(",") if k.strip()]


class APIKeyManager:
    """Rotates through multiple API keys with per-key cooldown on failure.

    - Keys are tried round-robin.
    - A key that returns 403/429 is temporarily disabled (cooldown 60s).
    - If all keys are in cooldown, the oldest cooldown is cleared to keep
      the service alive.
    """

    def __init__(self, keys: list[str], cooldown_seconds: int = 60):
        self._keys = keys
        self._cooldown_seconds = cooldown_seconds
        self._lock = threading.Lock()
        self._index = 0
        # key -> float (timestamp when cooldown ends)
        self._cooldown_until: dict[str, float] = {}

    @property
    def active_keys(self) -> list[str]:
        return list(self._keys)

    def get_key(self) -> str | None:
        """Return the next available API key, or None if none configured."""
        if not self._keys:
            return None
        with self._lock:
            now = time.time()
            # Try every key starting from current index
            for _ in range(len(self._keys)):
                candidate = self._keys[self._index]
                self._index = (self._index + 1) % len(self._keys)
                until = self._cooldown_until.get(candidate)
                if until is None or now >= until:
                    # Key is not in cooldown
                    return candidate
            # All keys are in cooldown — clear the oldest one to keep service alive
            oldest_key = min(self._cooldown_until, key=lambda k: self._cooldown_until[k])
            self._cooldown_until.pop(oldest_key, None)
            return oldest_key

    def mark_failed(self, key: str) -> None:
        """Put a key into cooldown after a failure (403, 429, etc.)."""
        with self._lock:
            self._cooldown_until[key] = time.time() + self._cooldown_seconds

    def mark_succeeded(self, key: str) -> None:
        """Clear any cooldown on a key after it succeeds (optional recovery)."""
        with self._lock:
            self._cooldown_until.pop(key, None)


_key_manager: APIKeyManager | None = None


def get_api_key_manager() -> APIKeyManager:
    """Lazy singleton: returns the APIKeyManager built from settings."""
    global _key_manager
    if _key_manager is None:
        _key_manager = APIKeyManager(settings.ai_api_keys)
    return _key_manager


def reload_api_keys() -> None:
    """Re-read keys from settings (useful after .env changes without restart)."""
    global _key_manager
    _key_manager = APIKeyManager(settings.ai_api_keys)


settings = Settings()
