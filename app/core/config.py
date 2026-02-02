from pydantic_settings import BaseSettings
from pydantic import field_validator


class Settings(BaseSettings):
    APP_NAME: str = "Hargeisa Tow API"

    # REQUIRED in .env
    JWT_SECRET: str
    JWT_ALG: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 60 * 24  # 1 day

    DATABASE_URL: str = "sqlite:///./tow.db"

    # Upload limits
    MAX_UPLOAD_MB: int = 8  # you can change this

    class Config:
        env_file = ".env"

    @field_validator("JWT_SECRET")
    @classmethod
    def validate_secret(cls, v: str) -> str:
        if not v or len(v.strip()) < 32:
            raise ValueError("JWT_SECRET must be set and at least 32 characters.")
        if "CHANGE_ME" in v.upper():
            raise ValueError("JWT_SECRET looks like a placeholder. Set a real secret.")
        return v.strip()


settings = Settings()

# from pydantic_settings import BaseSettings


# class Settings(BaseSettings):
#     APP_NAME: str = "Hargeisa Tow API"
#     JWT_SECRET: str = "CHANGE_ME_TO_A_LONG_RANDOM_SECRET"
#     JWT_ALG: str = "HS256"
#     JWT_EXPIRE_MINUTES: int = 60 * 24  # 1 day
#     DATABASE_URL: str = "sqlite:///./tow.db"

#     class Config:
#         env_file = ".env"


# settings = Settings()
