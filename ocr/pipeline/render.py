"""Render PDF/image pages to RGB numpy arrays."""

from __future__ import annotations

import os
from typing import Any

import numpy as np
from PIL import Image


def render_pages(path: str, *, dpi: int = 250, max_pages: int = 1) -> list[np.ndarray]:
    """Return list of RGB uint8 arrays (H, W, 3)."""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".pdf":
        return _render_pdf(path, dpi=dpi, max_pages=max_pages)
    return [_render_image(path)]


def _render_pdf(path: str, *, dpi: int, max_pages: int) -> list[np.ndarray]:
    import fitz  # PyMuPDF

    doc = fitz.open(path)
    try:
        pages: list[np.ndarray] = []
        zoom = dpi / 72.0
        matrix = fitz.Matrix(zoom, zoom)
        for index, page in enumerate(doc):
            if index >= max_pages:
                break
            pix = page.get_pixmap(matrix=matrix, alpha=False)
            img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
            if pix.n == 1:
                img = np.stack([img[:, :, 0]] * 3, axis=-1)
            elif pix.n == 4:
                img = img[:, :, :3]
            pages.append(img.copy())
        return pages
    finally:
        doc.close()


def _render_image(path: str) -> np.ndarray:
    with Image.open(path) as img:
        rgb = img.convert("RGB")
        return np.array(rgb)


def deskew(image: np.ndarray) -> tuple[np.ndarray, float]:
    """Light deskew via OpenCV minAreaRect on edges. Returns (image, angle_deg)."""
    import cv2

    if image.ndim != 3:
        return image, 0.0
    gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
    gray = cv2.bitwise_not(gray)
    thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]
    coords = np.column_stack(np.where(thresh > 0))
    if coords.size < 100:
        return image, 0.0
    angle = cv2.minAreaRect(coords)[-1]
    if angle < -45:
        angle = -(90 + angle)
    else:
        angle = -angle
    if abs(angle) < 0.3 or abs(angle) > 15:
        return image, 0.0
    h, w = image.shape[:2]
    matrix = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    rotated = cv2.warpAffine(
        image,
        matrix,
        (w, h),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REPLICATE,
    )
    return rotated, float(angle)


def save_rgb(path: str, image: np.ndarray) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    Image.fromarray(image).save(path, format="PNG", optimize=True)
