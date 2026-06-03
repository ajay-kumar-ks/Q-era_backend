from typing import Annotated

import os
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode


class Settings(BaseSettings):
    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }

    SECRET_KEY: str = Field("changeme", env="SECRET_KEY")
    DB_PATH: str = Field("database_files/qera.db", env="DB_PATH")
    DATABASE_URL: str | None = Field(None, env="DATABASE_URL")
    ALLOWED_ORIGINS: Annotated[list[str], NoDecode] = Field(
        default=["http://localhost:5173"],
        env="ALLOWED_ORIGINS"
    )
    DEBUG: bool = Field(True, env="DEBUG")
    CLOUDINARY_URL: str | None = Field(None, env="CLOUDINARY_URL")
    CLOUDINARY_CLOUD_NAME: str | None = Field(None, env="CLOUDINARY_CLOUD_NAME")
    CLOUDINARY_API_KEY: str | None = Field(None, env="CLOUDINARY_API_KEY")
    CLOUDINARY_API_SECRET: str | None = Field(None, env="CLOUDINARY_API_SECRET")
    CLOUDINARY_UPLOAD_FOLDER: str | None = Field("questions", env="CLOUDINARY_UPLOAD_FOLDER")

    @field_validator("ALLOWED_ORIGINS", mode="before")
    @classmethod
    def parse_allowed_origins(cls, v):
        if v is None or v == "":
            return ["http://localhost:5173"]
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

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


settings = Settings()
