import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(".env.local")

# Project root
PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"
SNAPSHOTS_DIR = DATA_DIR / "snapshots"
AUDIT_LOGS_DIR = DATA_DIR / "audit_logs"

# Database
DATABASE_PATH = DATA_DIR / "memory.db"

# Safety limits
MAX_FILES_PER_OPERATION = 1000
MAX_FILE_SIZE_MB = 5120
SNAPSHOT_RETENTION_HOURS = 24
MAX_SNAPSHOTS_PER_USER = 10

# Confirmation thresholds
AUTO_APPROVE_FILE_COUNT = 5  # Auto-approve if <= 5 files
REQUIRE_CONFIRMATION_FILE_COUNT = 10  # Always confirm if > 10 files

# File type categories
FILE_TYPE_CATEGORIES = {
    "Documents": [".pdf", ".doc", ".docx", ".txt", ".rtf", ".odt", ".pages", ".md"],
    "Spreadsheets": [".xls", ".xlsx", ".csv", ".numbers", ".ods"],
    "Presentations": [".ppt", ".pptx", ".key", ".odp"],
    "Images": [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".svg", ".webp", ".heic", ".ico"],
    "Videos": [".mp4", ".mov", ".avi", ".mkv", ".wmv", ".flv", ".webm", ".m4v"],
    "Audio": [".mp3", ".wav", ".aac", ".flac", ".m4a", ".ogg", ".wma"],
    "Archives": [".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz"],
    "Code": [".py", ".js", ".jsx", ".ts", ".tsx", ".html", ".css", ".java", ".cpp", ".c", ".go", ".rs", ".rb", ".php",".md"],
    "Executables": [".exe", ".dmg", ".app", ".deb", ".rpm", ".msi"],
    "Data": [".json", ".xml", ".yaml", ".yml", ".toml", ".ini", ".sql"],
    "Other": []
}

# Logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FORMAT = os.getenv("LOG_FORMAT", "json")  # json or console

# Ensure directories exist
SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
AUDIT_LOGS_DIR.mkdir(parents=True, exist_ok=True)

class Settings:
    # OpenAI
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    # Deepgram
    DEEPGRAM_STT: str = os.getenv("DEEPGRAM_STT", "flux-general-en")
    DEEPGRAM_TTS: str = os.getenv("DEEPGRAM_TTS", "aura-2-thalia-en")


# Singleton-style access
settings = Settings()