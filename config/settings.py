import os
from pathlib import Path
from dotenv import load_dotenv
from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import Field

# Load environment variables from .env.local
load_dotenv(".env.local")

class Settings(BaseSettings):
    """Application settings with validation and environment support"""

    # Project Directories
    PROJECT_ROOT: Path = Path(__file__).parent.parent
    DATA_DIR: Path = PROJECT_ROOT / "data"
    SNAPSHOTS_DIR: Path = DATA_DIR / "snapshots"
    AUDIT_LOGS_DIR: Path = DATA_DIR / "audit_logs"
    
    # Ensure directories exist
    SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    AUDIT_LOGS_DIR.mkdir(parents=True, exist_ok=True)

    # Database
    DATABASE_PATH: Path = DATA_DIR / "memory.db"

    # Safety Limits
    MAX_FILES_PER_OPERATION: int = Field(default=1000, description="Max files per operation")
    MAX_FILE_SIZE_MB: int = Field(default=5120, description="Maximum file size to process")
    SNAPSHOT_RETENTION_HOURS: int = Field(default=24, description="Snapshot retention period in hours")
    MAX_SNAPSHOTS_PER_USER: int = Field(default=10, description="Max snapshots per user")

    # Confirmation Thresholds
    AUTO_APPROVE_FILE_COUNT: int = Field(default=5, description="Auto-approve if <= 5 files")
    REQUIRE_CONFIRMATION_FILE_COUNT: int = Field(default=10, description="Always confirm if > 10 files")

    # File Type Categories
    FILE_TYPE_CATEGORIES: dict = Field(default={
        "Documents": [".pdf", ".doc", ".docx", ".txt", ".rtf", ".odt", ".pages", ".md"],
        "Spreadsheets": [".xls", ".xlsx", ".csv", ".numbers", ".ods"],
        "Presentations": [".ppt", ".pptx", ".key", ".odp"],
        "Images": [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".svg", ".webp", ".heic", ".ico"],
        "Videos": [".mp4", ".mov", ".avi", ".mkv", ".wmv", ".flv", ".webm", ".m4v"],
        "Audio": [".mp3", ".wav", ".aac", ".flac", ".m4a", ".ogg", ".wma"],
        "Archives": [".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz"],
        "Code": [".py", ".js", ".jsx", ".ts", ".tsx", ".html", ".css", ".java", ".cpp", ".c", ".go", ".rs", ".rb", ".php", ".md"],
        "Executables": [".exe", ".dmg", ".app", ".deb", ".rpm", ".msi"],
        "Data": [".json", ".xml", ".yaml", ".yml", ".toml", ".ini", ".sql"],
        "Other": []
    })

    # API Keys
    OPENAI_API_KEY: str = Field(..., description="OpenAI API key")
    DEEPGRAM_API_KEY: str = Field(..., description="Deepgram API key")
    LIVEKIT_URL: str = Field(..., description="LiveKit server URL")
    LIVEKIT_API_KEY: str = Field(..., description="LiveKit API key")
    LIVEKIT_API_SECRET: str = Field(..., description="LiveKit API secret")
    MEM0_API_KEY: Optional[str] = Field(None, description="Mem0 API key")

    # Model Configuration
    OPENAI_MODEL: str = Field(default="gpt-4", description="OpenAI model to use")
    DEEPGRAM_STT: str = Field(default="nova-2", description="Deepgram STT model")
    DEEPGRAM_TTS: str = Field(default="aura-asteria-en", description="Deepgram TTS model")

    # Application Settings
    APP_NAME: str = Field(default="FileBuddy", description="Application name")
    APP_VERSION: str = Field(default="1.0.0", description="Application version")
    ENVIRONMENT: str = Field(default="development", description="Environment (development/staging/production)")
    DEBUG: bool = Field(default=False, description="Debug mode")

    # Rate Limiting
    MAX_REQUESTS_PER_MINUTE: int = Field(default=60, description="Max API requests per minute")
    MAX_FILE_OPERATIONS_PER_MINUTE: int = Field(default=100, description="Max file ops per minute")

    # Retry Configuration
    MAX_RETRIES: int = Field(default=3, description="Maximum retry attempts")
    RETRY_DELAY: float = Field(default=1.0, description="Initial retry delay in seconds")
    RETRY_BACKOFF: float = Field(default=2.0, description="Retry backoff multiplier")

    # Circuit Breaker
    CIRCUIT_BREAKER_THRESHOLD: int = Field(default=5, description="Failures before circuit opens")
    CIRCUIT_BREAKER_TIMEOUT: int = Field(default=60, description="Circuit breaker timeout in seconds")

    # Memory Configuration
    MEMORY_RETENTION_DAYS: int = Field(default=90, description="Memory retention period")
    MEMORY_CACHE_SIZE: int = Field(default=1000, description="Memory cache size")

    # File Operations
    MAX_BATCH_SIZE: int = Field(default=1000, description="Maximum batch operation size")
    ENABLE_UNDO: bool = Field(default=True, description="Enable undo functionality")
    MAX_UNDO_HISTORY: int = Field(default=50, description="Maximum undo history entries")

    # Logging
    LOG_LEVEL: str = Field(default="INFO", description="Logging level")
    LOG_FORMAT: str = Field(default="json", description="Log format (json/text)")
    LOG_FILE: Optional[str] = Field(default="logs/filebuddy.log", description="Log file path")

    # Health Check
    HEALTH_CHECK_INTERVAL: int = Field(default=60, description="Health check interval in seconds")

    # Timeouts (seconds)
    API_TIMEOUT: int = Field(default=30, description="API request timeout")
    FILE_OPERATION_TIMEOUT: int = Field(default=300, description="File operation timeout")

    # Logging settings from environment
    LOG_LEVEL_ENV: str = os.getenv("LOG_LEVEL", "INFO")
    LOG_FORMAT_ENV: str = os.getenv("LOG_FORMAT", "json")  # json or console

    class Config:
        env_file = ".env.local"
        env_file_encoding = "utf-8"
        case_sensitive = True

# Singleton-style access
settings = Settings()

def is_production() -> bool:
    """Check if running in production environment"""
    return settings.ENVIRONMENT == "production"


def is_development() -> bool:
    """Check if running in development environment"""
    return settings.ENVIRONMENT == "development"


def get_log_level() -> str:
    """Get appropriate log level based on environment"""
    if is_production():
        return "WARNING"
    elif settings.DEBUG:
        return "DEBUG"
    return settings.LOG_LEVEL