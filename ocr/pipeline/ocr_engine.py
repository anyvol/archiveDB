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
    "format": "Aa0123456789×xХх*",
    "scale": "0123456789:.,",
    "digits": "0123456789",
    "date": "0123456789.-/",
    "fio": None,
    "text": None,
}


def ocr_cell(image: np.ndarray, *, category: str | None = None) -> dict[str, Any]:
    """OCR a cell image. Returns {raw, value, conf}."""
    if image.size == 0 or image.shape[0] < 2 or image.shape[1] < 2:
        return {"raw": None, "value": None, "conf": 0.0}

    if engine_name() == "paddleocr":
        return _ocr_paddle(image)
    return _ocr_tesseract(image, category=category)


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
        text = text.replace(" ", "").upper().replace("Х", "X").replace("*", "x")
        text = text.replace("×", "x")
        m = re.search(r"A[0-5](?:X[0-9]+)?", text, re.I)
        if m:
            code = m.group(0).upper().replace("X", "x")
            # map A3x3 style
            if "x" in code:
                parts = code.split("x")
                text = f"{parts[0]}x{parts[1]}" if len(parts) == 2 else code
            else:
                text = code
    elif category == "fio":
        text = text.title() if text.isupper() else text
    elif category in {"digits", "scale", "sheet", "sheets_total"}:
        text = re.sub(r"[^\d:.,]", "", text)
    return text or None


def _normalize_date(text: str) -> str | None:
    digits = re.findall(r"\d+", text)
    if len(digits) >= 3:
        d, m, y = digits[0], digits[1], digits[2]
        if len(y) == 2:
            y = "20" + y
        if len(d) == 1:
            d = "0" + d
        if len(m) == 1:
            m = "0" + m
        if len(y) == 4:
            return f"{y}-{m}-{d}"  # HTML date input
    return text.strip() or None
