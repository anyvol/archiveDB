import os

from dotenv import load_dotenv

load_dotenv()

ROOT_PATH = os.getenv("ROOT_PATH", "").rstrip("/")
PUBLIC_HTTPS_PORT = os.getenv("PUBLIC_HTTPS_PORT", os.getenv("HTTPS_PORT", "")).strip()

BACKUP_HOST_PATH = os.getenv("BACKUP_HOST_PATH", "./backups")
BACKUP_RETENTION_DAYS = int(os.getenv("BACKUP_RETENTION_DAYS", "30"))
BACKUP_AGENT_URL = os.getenv("BACKUP_AGENT_URL", "http://backup:9002").rstrip("/")
BACKUP_AGENT_TOKEN = os.getenv("BACKUP_AGENT_TOKEN", "").strip()
OPS_AGENT_URL = os.getenv("OPS_AGENT_URL", "http://ops-agent:9001").rstrip("/")
OPS_AGENT_TOKEN = os.getenv("OPS_AGENT_TOKEN", "").strip()

SMTP_HOST = os.getenv("SMTP_HOST", "").strip()
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "").strip()
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "").strip()
SMTP_FROM = os.getenv("SMTP_FROM", "").strip()
SMTP_USE_TLS = os.getenv("SMTP_USE_TLS", "true").lower() in ("1", "true", "yes")
ALLOWED_EMAIL_DOMAINS = {
    d.strip().lower()
    for d in os.getenv("ALLOWED_EMAIL_DOMAINS", "").split(",")
    if d.strip()
}

_VERSION_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "VERSION")


def read_version() -> str:
    with open(_VERSION_FILE, encoding="utf-8") as f:
        return f.read().strip()


SERVICE_VERSION = read_version()

VAPID_PUBLIC_KEY = os.getenv("VAPID_PUBLIC_KEY", "").strip()
VAPID_PRIVATE_KEY = os.getenv("VAPID_PRIVATE_KEY", "").strip()
VAPID_SUBJECT = os.getenv("VAPID_SUBJECT", "mailto:admin@example.com")
VAPID_CLAIMS = {"sub": VAPID_SUBJECT}

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

os.makedirs(UPLOAD_DIR, exist_ok=True)


def url_path(path: str) -> str:
    if not path.startswith("/"):
        path = f"/{path}"
    return f"{ROOT_PATH}{path}" if ROOT_PATH else path


def app_scope() -> str:
    scope = url_path("/")
    return scope if scope.endswith("/") else f"{scope}/"
