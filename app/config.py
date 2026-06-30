import os

from dotenv import load_dotenv

load_dotenv()

ROOT_PATH = os.getenv("ROOT_PATH", "").rstrip("/")

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
