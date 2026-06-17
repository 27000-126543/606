from pydantic_settings import BaseSettings
from typing import List, Optional
import os


class Settings(BaseSettings):
    APP_NAME: str = "运维异常检测与自动化处理系统"
    APP_ENV: str = "development"
    APP_DEBUG: bool = True
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000

    DB_TYPE: str = "sqlite"
    DB_HOST: str = "localhost"
    DB_PORT: int = 5432
    DB_USER: str = "postgres"
    DB_PASSWORD: str = "postgres"
    DB_NAME: str = "ops_monitor"
    DB_FILE: str = "./data/ops_monitor.db"
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 50

    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: Optional[str] = None
    REDIS_DB: int = 0
    REDIS_POOL_SIZE: int = 50

    KAFKA_BROKERS: str = "localhost:9092"
    KAFKA_TOPIC_LOGS: str = "ops_logs"
    KAFKA_TOPIC_ANOMALIES: str = "ops_anomalies"
    KAFKA_GROUP_ID: str = "ops_consumer_group"
    KAFKA_BATCH_SIZE: int = 10000
    KAFKA_AUTO_COMMIT_INTERVAL_MS: int = 5000

    JWT_SECRET_KEY: str = "your-super-secret-key-change-this-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 120
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    MAX_WORKERS: int = 8
    LOG_PROCESS_CONCURRENCY: int = 4
    ANOMALY_DETECT_INTERVAL: int = 60

    REPORT_EXPORT_DIR: str = "./exports"
    MAX_EXPORT_FILE_AGE: int = 7

    SMTP_HOST: Optional[str] = None
    SMTP_PORT: int = 587
    SMTP_USER: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    SMTP_FROM_EMAIL: Optional[str] = None

    LOG_LEVEL: str = "INFO"
    LOG_FILE: str = "./logs/app.log"
    LOG_MAX_BYTES: int = 10 * 1024 * 1024
    LOG_BACKUP_COUNT: int = 10

    @property
    def DATABASE_URL(self) -> str:
        if self.DB_TYPE.lower() == "sqlite":
            db_path = os.path.abspath(self.DB_FILE)
            os.makedirs(os.path.dirname(db_path), exist_ok=True)
            return f"sqlite+aiosqlite:///{db_path}"
        return f"postgresql+asyncpg://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"

    @property
    def SYNC_DATABASE_URL(self) -> str:
        if self.DB_TYPE.lower() == "sqlite":
            db_path = os.path.abspath(self.DB_FILE)
            os.makedirs(os.path.dirname(db_path), exist_ok=True)
            return f"sqlite:///{db_path}"
        return f"postgresql://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"

    @property
    def KAFKA_BROKERS_LIST(self) -> List[str]:
        return [b.strip() for b in self.KAFKA_BROKERS.split(",") if b.strip()]

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()

os.makedirs(settings.REPORT_EXPORT_DIR, exist_ok=True)
os.makedirs(os.path.dirname(settings.LOG_FILE), exist_ok=True)
if settings.DB_TYPE.lower() == "sqlite":
    os.makedirs(os.path.dirname(settings.DB_FILE), exist_ok=True)
