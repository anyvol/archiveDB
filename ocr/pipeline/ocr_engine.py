"""OCR engine wrapper — Tesseract (rus) by default; optional PaddleOCR if installed."""

from __future__ import annotations

import logging
import os
import re
from typing import Any

import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)

_ENGINE = os.getenv("OCR_ENGINE", "auto").strip().lower()  # auto | tesseract | paddle
_paddle_reader = None
_paddle_failed = False


def engine_name() -> str:
    if _ENGINE == "paddle" or (_ENGINE == "auto" and _try_paddle()):
        return "paddleocr"
    return "tesseract"


def _try_paddle() -> bool:
    global _paddle_reader, _paddle_failed
    if _paddle_failed:
        return False
    if _paddle_reader is not None:
        return True
    try:
        from paddleocr import PaddleOCR  # type: ignore

        _paddle_reader = PaddleOCR(use_angle_cls=True, lang="ru", show_log=False)
        return True
    except Exception as exc:
        logger.warning("PaddleOCR unavailable, using Tesseract: %s", exc)
        _paddle_failed = True
        return False


_WHITELISTS = {
    "designation": "ABCDEFGHIJKLMNOPQRSTUVWXYZАБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ0123456789.-",
    "format": "AaАа0123456789×xХх*",
    "scale": "0123456789:.,",
    "digits": "0123456789",
    "date": "0123456789.-/",
    "fio": None,
    "text": None,
    "signature": None,
}

# Dark-pixel ratio above this → treat signature ROI as filled.
_SIGNATURE_INK_RATIO = float(os.getenv("OCR_SIGNATURE_INK_RATIO", "0.02"))


def ocr_cell(image: np.ndarray, *, category: str | None = None) -> dict[str, Any]:
    """OCR a cell image. Returns {raw, value, conf}."""
    if image.size == 0 or image.shape[0] < 2 or image.shape[1] < 2:
        return {"raw": None, "value": None, "conf": 0.0}

    if category == "signature":
        return detect_signature_present(image)

    if engine_name() == "paddleocr":
        result = _ocr_paddle(image)
        result["value"] = _normalize_value(result.get("raw"), category)
        return result
    return _ocr_tesseract(image, category=category)


def detect_signature_present(image: np.ndarray) -> dict[str, Any]:
    """If the ROI has any meaningful ink/content, assume a signature is present."""
    if image.ndim == 3:
        gray = image.mean(axis=2)
    else:
        gray = image.astype(float)
    # Ignore near-white background; count darker strokes
    dark = float(np.count_nonzero(gray < 200))
    ratio = dark / float(gray.size) if gray.size else 0.0
    present = ratio >= _SIGNATURE_INK_RATIO
    return {
        "raw": f"{ratio:.4f}",
        "value": "true" if present else "false",
        "conf": round(min(0.95, 0.5 + ratio * 5), 3),
    }


def _ocr_tesseract(image: np.ndarray, *, category: str | None) -> dict[str, Any]:
    import pytesseract

    pil = Image.fromarray(image)
    # Upscale small cells for better recognition
    if pil.width < 120 or pil.height < 40:
        scale = max(2, int(140 / max(pil.height, 1)))
        pil = pil.resize((pil.width * scale, pil.height * scale), Image.Resampling.LANCZOS)

    config_parts = ["--psm", "6", "-l", "rus+eng"]
    whitelist = _WHITELISTS.get(category or "")
    if whitelist:
        config_parts.append(f"-c tessedit_char_whitelist={whitelist}")
    config = " ".join(config_parts)

    try:
        data = pytesseract.image_to_data(pil, config=config, output_type=pytesseract.Output.DICT)
    except Exception as exc:
        logger.warning("tesseract failed: %s", exc)
        return {"raw": None, "value": None, "conf": 0.0}

    words: list[str] = []
    confs: list[float] = []
    for text, conf in zip(data.get("text", []), data.get("conf", [])):
        token = (text or "").strip()
        try:
            c = float(conf)
        except (TypeError, ValueError):
            c = -1.0
        if not token or c < 0:
            continue
        words.append(token)
        confs.append(c / 100.0)

    raw = " ".join(words).strip() or None
    value = _normalize_value(raw, category)
    mean_conf = float(sum(confs) / len(confs)) if confs else (0.0 if not raw else 0.4)
    return {"raw": raw, "value": value, "conf": round(mean_conf, 3)}


def _ocr_paddle(image: np.ndarray) -> dict[str, Any]:
    assert _paddle_reader is not None
    try:
        result = _paddle_reader.ocr(image, cls=True)
    except Exception as exc:
        logger.warning("paddle ocr failed: %s", exc)
        return {"raw": None, "value": None, "conf": 0.0}

    lines: list[str] = []
    confs: list[float] = []
    # result: list per image → list of [box, (text, conf)]
    blocks = result[0] if result else None
    if not blocks:
        return {"raw": None, "value": None, "conf": 0.0}
    for item in blocks:
        if not item or len(item) < 2:
            continue
        text, conf = item[1][0], float(item[1][1])
        token = (text or "").strip()
        if not token:
            continue
        lines.append(token)
        confs.append(conf)
    raw = " ".join(lines).strip() or None
    mean_conf = float(sum(confs) / len(confs)) if confs else 0.0
    return {"raw": raw, "value": raw, "conf": round(mean_conf, 3)}


def _normalize_value(raw: str | None, category: str | None) -> str | None:
    if not raw:
        return None
    text = re.sub(r"\s+", " ", raw).strip()
    if category == "designation":
        text = text.replace(" ", "").upper()
        text = text.replace(",", ".")
    elif category == "date":
        text = _normalize_date(text)
    elif category == "format":
        # Cyrillic А/а → Latin A so dropdown codes (A4, A3x3, …) match
        text = (
            text.replace(" ", "")
            .replace("А", "A")
            .replace("а", "A")
            .upper()
            .replace("Х", "X")
            .replace("*", "x")
            .replace("×", "x")
        )
        m = re.search(r"A[0-5](?:X[0-9]+)?", text, re.I)
        if m:
            code = m.group(0).upper().replace("X", "x")
            if "x" in code:
                parts = code.split("x")
                text = f"{parts[0]}x{parts[1]}" if len(parts) == 2 else code
            else:
                text = code
        else:
            return None
    elif category == "fio":
        text = text.title() if text.isupper() else text
    elif category == "signature":
        low = text.casefold()
        if low in {"1", "true", "yes", "да", "y"}:
            return "true"
        if low in {"0", "false", "no", "нет", "n"}:
            return "false"
        return "true" if text.strip() else "false"
    elif category in {"digits", "scale", "sheet", "sheets_total"}:
        text = re.sub(r"[^\d:.,]", "", text)
    return text or None


def _normalize_date(text: str) -> str | None:
    """Return YYYY-MM-DD for HTML date inputs, or None if unparseable.

    Stamps often use dd.mm.yy (two-digit year → 20xx).
    """
    if not text:
        return None
    cleaned = text.replace(",", ".").replace("·", ".").replace(" ", "")
    m_iso = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", cleaned)
    if m_iso:
        return m_iso.group(0)
    digits = re.findall(r"\d+", text)
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
            return None
        if len(y) == 4 and 1 <= mi <= 12 and 1 <= di <= 31 and 1990 <= yi <= 2099:
            return f"{yi:04d}-{mi:02d}-{di:02d}"
    compact = re.sub(r"\D", "", text)
    if len(compact) == 6 and compact.isdigit():
        d, m, y = int(compact[0:2]), int(compact[2:4]), int("20" + compact[4:6])
        if 1 <= m <= 12 and 1 <= d <= 31:
            return f"{y:04d}-{m:02d}-{d:02d}"
    return None
