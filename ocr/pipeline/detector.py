"""Optional learned stamp detector (phase 3).

If ``OCR_STAMP_DETECTOR_PATH`` points to a YOLO/Ultralytics ``.pt`` (or ONNX) model,
detect the title-block bbox on the page and return normalized ``[x0,y0,x1,y1]``.
Otherwise return ``None`` so the pipeline falls back to format templates / defaults.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

_DETECTOR_PATH = os.getenv("OCR_STAMP_DETECTOR_PATH", "").strip()
_MIN_CONF = float(os.getenv("OCR_STAMP_DETECTOR_MIN_CONF", "0.35"))
_model = None
_model_failed = False


def detector_enabled() -> bool:
    return bool(_DETECTOR_PATH) and os.path.isfile(_DETECTOR_PATH) and not _model_failed


def detect_stamp_roi(page: np.ndarray) -> tuple[float, float, float, float] | None:
    """Return normalized stamp ROI or None."""
    if not detector_enabled():
        return None
    model = _load_model()
    if model is None:
        return None
    try:
        results = model.predict(source=page, verbose=False, conf=_MIN_CONF)
    except Exception as exc:
        logger.warning("stamp detector predict failed: %s", exc)
        return None
    if not results:
        return None
    boxes = getattr(results[0], "boxes", None)
    if boxes is None or len(boxes) == 0:
        return None
    # Pick highest-confidence box
    try:
        confs = boxes.conf.tolist()
        xyxy = boxes.xyxy.tolist()
    except Exception:
        return None
    best_i = int(max(range(len(confs)), key=lambda i: confs[i]))
    x0, y0, x1, y1 = xyxy[best_i]
    h, w = page.shape[:2]
    if w <= 0 or h <= 0:
        return None
    norm = (
        max(0.0, min(1.0, x0 / w)),
        max(0.0, min(1.0, y0 / h)),
        max(0.0, min(1.0, x1 / w)),
        max(0.0, min(1.0, y1 / h)),
    )
    if norm[2] <= norm[0] + 0.02 or norm[3] <= norm[1] + 0.02:
        return None
    logger.info("stamp detector hit conf=%.3f roi=%s", confs[best_i], [round(v, 3) for v in norm])
    return norm


def detector_status() -> dict[str, Any]:
    return {
        "path": _DETECTOR_PATH or None,
        "enabled": detector_enabled(),
        "min_conf": _MIN_CONF,
        "failed": _model_failed,
    }


def _load_model():
    global _model, _model_failed
    if _model_failed:
        return None
    if _model is not None:
        return _model
    if not _DETECTOR_PATH or not os.path.isfile(_DETECTOR_PATH):
        return None
    try:
        from ultralytics import YOLO  # type: ignore

        _model = YOLO(_DETECTOR_PATH)
        return _model
    except Exception as exc:
        logger.warning("stamp detector unavailable (%s): %s", _DETECTOR_PATH, exc)
        _model_failed = True
        return None
