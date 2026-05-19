from pydantic_settings import BaseSettings, SettingsConfigDict


DEFAULT_SECRET_KEY = "change-me-in-production"


class Settings(BaseSettings):
    ENVIRONMENT: str = "development"
    DATABASE_URL: str = "sqlite+aiosqlite:///./kitobxon.db"
    SECRET_KEY: str = DEFAULT_SECRET_KEY
    ALGORITHM: str = "HS256"
    JWT_ISSUER: str = "kitobxon-api"
    JWT_AUDIENCE: str = "kitobxon-api"
    ACCESS_TOKEN_EXPIRE_HOURS: int = 24
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30
    INITIAL_ADMIN_EMAIL: str = ""
    INITIAL_ADMIN_PASSWORD: str = ""
    STORAGE_BACKEND: str = "local"  # "local" | "supabase"
    LOCAL_STORAGE_PATH: str = "./uploads"
    SUPABASE_URL: str = ""
    SUPABASE_KEY: str = ""
    SUPABASE_BUCKET: str = "kitobxon"
    MAX_BOOK_FILE_SIZE: int = 50 * 1024 * 1024    # 50MB
    MAX_AUDIO_FILE_SIZE: int = 200 * 1024 * 1024   # 200MB
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_STORAGE_URL: str = "memory://"
    RUN_MIGRATIONS_ON_STARTUP: bool = False
    CORS_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:8080"]
    
    model_config = SettingsConfigDict(env_file=".env")


settings = Settings()
