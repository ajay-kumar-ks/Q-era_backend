import os
from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {
        "env_file": os.getenv("ENV_FILE", ".env"),
        "env_file_encoding": "utf-8",
    }

    SECRET_KEY: str = Field("changeme", env="SECRET_KEY")
    DB_PATH: str = Field("../database/qera.db", env="DB_PATH")
    DATABASE_URL: str | None = Field(None, env="DATABASE_URL")
    ALLOWED_ORIGIN: str = Field("http://localhost:5173", env="ALLOWED_ORIGIN")
    DEBUG: bool = Field(True, env="DEBUG")
    CLOUDINARY_URL: str | None = Field(None, env="CLOUDINARY_URL")
    CLOUDINARY_CLOUD_NAME: str | None = Field(None, env="CLOUDINARY_CLOUD_NAME")
    CLOUDINARY_API_KEY: str | None = Field(None, env="CLOUDINARY_API_KEY")
    CLOUDINARY_API_SECRET: str | None = Field(None, env="CLOUDINARY_API_SECRET")
    CLOUDINARY_UPLOAD_FOLDER: str | None = Field("questions", env="CLOUDINARY_UPLOAD_FOLDER")


settings = Settings()
