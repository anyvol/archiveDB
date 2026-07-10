"""OCR field normalization helpers for review prefill and format templates."""

from __future__ import annotations

import re

from app.document_format import DOCUMENT_FORMAT_CODES, is_valid_document_format
from app.models import DOC_KIND_CODES

_DESIGNATION_SERIAL = re.compile(
    r"^(\d{1,4})(?:-(\d{1,2}))?([A-Za-zА-Яа-яЁё0-9]{0,3})?$"
)

_CYR_A = str.maketrans({"А": "A", "а": "A", "а": "a"})  # noqa: RUF001 — Cyrillic А


def coerce_document_format(value: str | None) -> str:
    """Map OCR/geometry format text to a valid DOCUMENT_FORMATS code, or ''."""
    if not value:
        return ""
    text = str(value).strip().replace(" ", "")
    text = text.translate(str.maketrans({"А": "A", "а": "A"}))
    text = text.upper().replace("Х", "X").replace("×", "X").replace("*", "X")
    if is_valid_document_format(text):
        return text
    # A3X3 → A3x3
    m = re.search(r"A([0-5])(?:X([0-9]+))?", text, re.I)
    if not m:
        return ""
    code = f"A{m.group(1)}"
    if m.group(2):
        code = f"{code}x{m.group(2)}"
    return code if is_valid_document_format(code) else ""


def normalize_ocr_date(value: str | None) -> str:
    """Return YYYY-MM-DD for HTML date inputs, or empty string."""
    if not value:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    iso = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", text)
    if iso:
        return text
    for fmt in ("%d.%m.%Y", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%y", "%d/%m/%y"):
        try:
            from datetime import datetime

            return datetime.strptime(text, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    digits = re.findall(r"\d+", text)
    if len(digits) >= 3:
        d, m, y = digits[0], digits[1], digits[2]
        if len(y) == 2:
            y = "20" + y
        try:
            di, mi, yi = int(d), int(m), int(y)
        except ValueError:
            return ""
        if len(y) == 4 and 1 <= mi <= 12 and 1 <= di <= 31:
            return f"{yi:04d}-{mi:02d}-{di:02d}"
    return ""


def parse_designation_parts(designation: str | None) -> dict[str, str]:
    """Split designation into org/class/reg/execution/doc_kind."""
    empty = {
        "org_code": "",
        "class_code": "",
        "reg_number": "",
        "execution": "",
        "doc_kind_code": "",
    }
    if not designation:
        return empty
    cleaned = designation.replace(" ", "")
    parts = cleaned.split(".")
    org_code = class_code = reg_number = execution = doc_kind_code = ""
    if len(parts) >= 3:
        org_code = parts[0]
        class_code = parts[1]
        m = _DESIGNATION_SERIAL.match(parts[2])
        if m:
            reg_number = m.group(1)
            execution = m.group(2) or ""
            doc_kind_code = m.group(3) or ""
    elif len(parts) == 2:
        org_code = parts[0]
        class_code = parts[1]

    if not doc_kind_code:
        doc_kind_code = extract_doc_kind_from_text(cleaned)
    else:
        doc_kind_code = match_doc_kind_code(doc_kind_code) or doc_kind_code

    return {
        "org_code": org_code,
        "class_code": class_code,
        "reg_number": reg_number,
        "execution": execution,
        "doc_kind_code": doc_kind_code if doc_kind_code in DOC_KIND_CODES else (match_doc_kind_code(doc_kind_code) or ""),
    }


def match_doc_kind_code(raw: str | None) -> str:
    if not raw:
        return ""
    needle = raw.strip()
    for code in DOC_KIND_CODES:
        if code.casefold() == needle.casefold():
            return code
    return ""


def extract_doc_kind_from_text(designation: str | None) -> str:
    """If designation ends with a known doc kind (СБ, СП, …), return that code."""
    if not designation:
        return ""
    cleaned = designation.replace(" ", "")
    # Longest first so Э2 wins over shorter prefixes
    for code in sorted(DOC_KIND_CODES, key=len, reverse=True):
        if cleaned.endswith(code) or cleaned.casefold().endswith(code.casefold()):
            return code
    return ""


def parse_bool_flag(value: str | bool | None) -> bool | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    low = str(value).strip().casefold()
    if low in {"1", "true", "yes", "да", "y", "on"}:
        return True
    if low in {"0", "false", "no", "нет", "n", "off"}:
        return False
    return None


# Silence unused — keep DOCUMENT_FORMAT_CODES import for callers/tests
_ = DOCUMENT_FORMAT_CODES
