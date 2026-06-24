import os

from dotenv import load_dotenv

load_dotenv()

UPLOAD_DIR = os.getenv("UPLOAD_DIR", "uploaded_files")
MAX_UPLOAD_SIZE_MB = int(os.getenv("MAX_UPLOAD_SIZE_MB", "10"))
ALLOWED_EXTENSIONS = {
    ext.strip().lower()
    for ext in os.getenv(
        "ALLOWED_EXTENSIONS",
        ".pdf,.doc,.docx,.png,.jpg,.jpeg,.tif,.tiff,.dwg,.dxf",
    ).split(",")
    if ext.strip()
}

# URL prefix when served behind reverse proxy (e.g. /archive). Empty for direct dev access.
APP_BASE_PATH = os.getenv("APP_BASE_PATH", "/archive").rstrip("/")
AUTO_CREATE_TABLES = os.getenv("AUTO_CREATE_TABLES", "false").lower() == "true"


def app_path(path: str) -> str:
    """Build outward-facing path with APP_BASE_PATH prefix."""
    if not path.startswith("/"):
        path = f"/{path}"
    return f"{APP_BASE_PATH}{path}" if APP_BASE_PATH else path


def cookie_path() -> str:
    return APP_BASE_PATH or "/"


os.makedirs(UPLOAD_DIR, exist_ok=True)
