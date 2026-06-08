import os
from pydantic import Field, field_validator, ConfigDict
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = ConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    SECRET_KEY: str = Field("changeme", env="SECRET_KEY")
    DB_PATH: str = Field("database_files/qera.db", env="DB_PATH")
    DATABASE_URL: str | None = Field(None, env="DATABASE_URL")
    ALLOWED_ORIGINS_STR: str = Field(
        default="http://localhost:5173",
        env="ALLOWED_ORIGINS"
    )
    DEBUG: bool = Field(True, env="DEBUG")
    CLOUDINARY_URL: str | None = Field(None, env="CLOUDINARY_URL")
    CLOUDINARY_CLOUD_NAME: str | None = Field(None, env="CLOUDINARY_CLOUD_NAME")
    CLOUDINARY_API_KEY: str | None = Field(None, env="CLOUDINARY_API_KEY")
    CLOUDINARY_API_SECRET: str | None = Field(None, env="CLOUDINARY_API_SECRET")
    CLOUDINARY_UPLOAD_FOLDER: str | None = Field("questions", env="CLOUDINARY_UPLOAD_FOLDER")

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


settings = Settings()
