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

os.makedirs(UPLOAD_DIR, exist_ok=True)
