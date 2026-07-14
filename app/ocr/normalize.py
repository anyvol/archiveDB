"""OCR field normalization helpers for review prefill and format templates."""

from __future__ import annotations

import re
from datetime import datetime

from app.document_format import is_valid_document_format
from app.models import DOC_KIND_CODES

_DESIGNATION_SERIAL = re.compile(
    r"^(\d{1,4})(?:-(\d{1,2}))?([A-Za-zА-Яа-яЁё0-9]{0,3})?$"
)

# Latin letters that OCR often emits instead of visually similar Cyrillic (stamp text).
_LATIN_TO_CYR = str.maketrans(
    {
        "A": "А",
        "a": "А",
        "B": "В",
        "b": "В",
        "C": "С",
        "c": "С",
        "E": "Е",
        "e": "Е",
        "H": "Н",
        "h": "Н",
        "K": "К",
        "k": "К",
        "M": "М",
        "m": "М",
        "O": "О",
        "o": "О",
        "P": "Р",
        "p": "Р",
        "T": "Т",
        "t": "Т",
        "X": "Х",
        "x": "Х",
        "Y": "У",
        "y": "У",
    }
)

# For doc-kind codes, Latin B is usually Cyrillic Б (СБ), not В.
_KIND_LATIN_TO_CYR = str.maketrans(
    {
        "A": "А",
        "B": "Б",
        "C": "С",
        "E": "Е",
        "H": "Н",
        "K": "К",
        "M": "М",
        "O": "О",
        "P": "П",
        "T": "Т",
        "X": "Х",
        "Y": "У",
        "a": "А",
        "b": "Б",
        "c": "С",
        "e": "Е",
        "h": "Н",
        "k": "К",
        "m": "М",
        "o": "О",
        "p": "П",
        "t": "Т",
        "x": "Х",
        "y": "У",
    }
)

# Common OCR aliases → canonical DOC_KIND_CODES
_DOC_KIND_ALIASES = {
    "СБ": "СБ",
    "CB": "СБ",
    "СB": "СБ",
    "CБ": "СБ",
    "СВ": "СБ",  # B→В fold mistake
    "ГЧ": "ГЧ",
    "ТУ": "ТУ",
    "TY": "ТУ",
    "TУ": "ТУ",
    "Э2": "Э2",
    "E2": "Э2",
    "Е2": "Э2",
    "Е1": "Е1",
    "E1": "Е1",
    "РЭ": "РЭ",
    "PE": "РЭ",
    "PЭ": "РЭ",
    "ВП": "ВП",
    "BP": "ВП",
    "BП": "ВП",
    "ПС": "ПС",
    "PC": "ПС",
    "PС": "ПС",
}


def fold_latin_to_cyrillic(text: str | None) -> str:
    """Map Latin lookalikes to Cyrillic for fuzzy matching of org codes / stamp text."""
    if not text:
        return ""
    return str(text).translate(_LATIN_TO_CYR).upper().replace(" ", "")


def coerce_document_format(value: str | None) -> str:
    """Map OCR/geometry format text to a valid DOCUMENT_FORMATS code, or ''."""
    if not value:
        return ""
    text = str(value).strip().replace(" ", "")
    text = text.replace("А", "A").replace("а", "A")
    text = text.upper().replace("Х", "X").replace("×", "X").replace("*", "X")
    if is_valid_document_format(text):
        return text
    m = re.search(r"A([0-5])(?:X([0-9]+))?", text, re.I)
    if not m:
        return ""
    code = f"A{m.group(1)}"
    if m.group(2):
        code = f"{code}x{m.group(2)}"
    return code if is_valid_document_format(code) else ""


def normalize_ocr_date(value: str | None) -> str:
    """Return YYYY-MM-DD for HTML date inputs, or empty string.

    Stamps often use dd.mm.yy (two-digit year) — treated as 20xx.
    """
    if not value:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    # Strip common OCR noise around digits
    text = text.replace(",", ".").replace("·", ".").replace(" ", "")
    if re.match(r"^\d{4}-\d{2}-\d{2}$", text):
        return text
    for fmt in ("%d.%m.%Y", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%y", "%d/%m/%y", "%d-%m-%y"):
        try:
            return datetime.strptime(text, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    # Digits with any separators: 15.03.24 / 15 03 2024 / 150324
    digits = re.findall(r"\d+", str(value))
    if len(digits) >= 3:
        d, m, y = digits[0], digits[1], digits[2]
        if len(y) == 2:
            y = "20" + y
        if len(d) == 1:
            d = "0" + d
        if len(m) == 1:
            m = "0" + m
        try:
            di, mi, yi = int(d), int(m), int(y)
        except ValueError:
            return ""
        if len(y) == 4 and 1 <= mi <= 12 and 1 <= di <= 31 and 1990 <= yi <= 2099:
            return f"{yi:04d}-{mi:02d}-{di:02d}"
    # Compact 6 digits ddmmyy
    compact = re.sub(r"\D", "", str(value))
    if len(compact) == 6 and compact.isdigit():
        d, m, y = compact[0:2], compact[2:4], "20" + compact[4:6]
        try:
            di, mi, yi = int(d), int(m), int(y)
        except ValueError:
            return ""
        if 1 <= mi <= 12 and 1 <= di <= 31:
            return f"{yi:04d}-{mi:02d}-{di:02d}"
    if len(compact) == 8 and compact.isdigit():
        d, m, y = compact[0:2], compact[2:4], compact[4:8]
        try:
            di, mi, yi = int(d), int(m), int(y)
        except ValueError:
            return ""
        if 1 <= mi <= 12 and 1 <= di <= 31 and 1990 <= yi <= 2099:
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

    matched = match_doc_kind_code(doc_kind_code) or extract_doc_kind_from_text(cleaned)
    return {
        "org_code": org_code,
        "class_code": class_code,
        "reg_number": reg_number,
        "execution": execution,
        "doc_kind_code": matched,
    }


def match_doc_kind_code(raw: str | None) -> str:
    if not raw:
        return ""
    needle = raw.strip().replace(" ", "")
    if not needle:
        return ""
    # Direct / alias
    upper = needle.upper()
    if upper in _DOC_KIND_ALIASES:
        return _DOC_KIND_ALIASES[upper]
    if needle in DOC_KIND_CODES:
        return needle
    for code in DOC_KIND_CODES:
        if code.casefold() == needle.casefold():
            return code
    # Latin→Cyrillic folds (B as Б for kinds, and B as В)
    folded_kind = needle.translate(_KIND_LATIN_TO_CYR).upper()
    if folded_kind in _DOC_KIND_ALIASES:
        return _DOC_KIND_ALIASES[folded_kind]
    if folded_kind in DOC_KIND_CODES:
        return folded_kind
    folded_ve = fold_latin_to_cyrillic(needle)
    if folded_ve in _DOC_KIND_ALIASES:
        return _DOC_KIND_ALIASES[folded_ve]
    if folded_ve in DOC_KIND_CODES:
        return folded_ve
    return ""


def extract_doc_kind_from_text(designation: str | None) -> str:
    """If designation ends with a known doc kind (СБ, СП, …), return that code."""
    if not designation:
        return ""
    cleaned = designation.replace(" ", "")
    # Try raw suffix, then folded variants
    candidates = [
        cleaned,
        cleaned.translate(_KIND_LATIN_TO_CYR),
        fold_latin_to_cyrillic(cleaned),
    ]
    for text in candidates:
        for code in sorted(DOC_KIND_CODES, key=len, reverse=True):
            if text.endswith(code) or text.casefold().endswith(code.casefold()):
                return code
            # Alias endings (e.g. ...001CB)
            for alias, canon in _DOC_KIND_ALIASES.items():
                if canon == code and text.upper().endswith(alias.upper()):
                    return code
    # Last 1–3 chars as kind
    tail = cleaned[-3:] if len(cleaned) >= 2 else cleaned
    for n in (3, 2, 1):
        if len(tail) >= n:
            hit = match_doc_kind_code(cleaned[-n:])
            if hit:
                return hit
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


def date_hint_from_field(entry: dict | None) -> dict[str, str]:
    """Return {raw, normalized} for UI hints under date inputs."""
    entry = entry or {}
    raw = entry.get("raw") or entry.get("value") or ""
    raw_s = str(raw).strip() if raw is not None else ""
    normalized = normalize_ocr_date(entry.get("value")) or normalize_ocr_date(raw_s)
    return {"raw": raw_s, "normalized": normalized}
