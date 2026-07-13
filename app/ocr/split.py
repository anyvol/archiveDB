"""Split OCR source PDFs into SB / specification subsets."""

from __future__ import annotations

import os
import tempfile
from typing import Any

from pypdf import PdfReader, PdfWriter


def _write_pages(source_path: str, page_indices: list[int], dest_path: str) -> None:
    reader = PdfReader(source_path)
    writer = PdfWriter()
    for index in page_indices:
        if 0 <= index < len(reader.pages):
            writer.add_page(reader.pages[index])
    if not writer.pages:
        raise ValueError("no pages selected for output PDF")
    os.makedirs(os.path.dirname(dest_path) or ".", exist_ok=True)
    with open(dest_path, "wb") as handle:
        writer.write(handle)


def split_source_file(
    source_path: str,
    geometry: dict[str, Any],
    *,
    work_dir: str | None = None,
) -> dict[str, str | None]:
    """Return paths for assembly and specification PDFs (temp files)."""
    role = geometry.get("document_role")
    if role == "combined_a4":
        return {"assembly": source_path, "specification": None}

    if role != "assembly_with_spec_pages":
        return {"assembly": source_path, "specification": None}

    assembly_pages = geometry.get("assembly_page_indices") or [0]
    spec_pages = geometry.get("spec_page_indices") or []
    if not spec_pages:
        return {"assembly": source_path, "specification": None}

    base_dir = work_dir or tempfile.mkdtemp(prefix="ocr_split_")
    assembly_path = os.path.join(base_dir, "assembly.pdf")
    spec_path = os.path.join(base_dir, "specification.pdf")
    _write_pages(source_path, assembly_pages, assembly_path)
    _write_pages(source_path, spec_pages, spec_path)
    return {"assembly": assembly_path, "specification": spec_path}
