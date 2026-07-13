"""Helpers for electronic specifications (GOST 2.055) and SB linkage."""

from __future__ import annotations

import re
from typing import Any

from fastapi import HTTPException
from rapidfuzz import fuzz
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import joinedload

from app.designation_helpers import build_designation, parse_execution_input
from app.models import (
    DOC_KIND_CODES,
    BaseDocument,
    DesignDocument,
    DocumentStatus,
    GOST_SPEC_SECTIONS,
    SPECIFICATION_FOLDER,
    SpecificationEntry,
    SpecificationEntrySource,
    User,
)
from app.notifications import get_document_designation
from app.ocr.normalize import match_doc_kind_code, parse_designation_parts

_ASSEMBLY_KIND_SUFFIXES = ("СБ",)
_SPEC_BASE_RE = re.compile(
    r"^([A-ZА-ЯЁ]{2,8}\.[A-ZА-ЯЁ0-9]{2,8}\.\d{3}(?:-[0-9]{1,2})?)",
    re.IGNORECASE,
)
_LINK_MATCH_THRESHOLD = 88


def strip_assembly_kind_suffix(designation: str | None) -> str:
    """ФЕТР.301524.002СБ → ФЕТР.301524.002 (base designation for spec lookup)."""
    text = (designation or "").strip()
    if not text:
        return ""
    parts = parse_designation_parts(text)
    base = parts.get("org_code", "")
    cls = parts.get("class_code", "")
    reg = parts.get("reg_number", "")
    execution = parts.get("execution", "")
    if base and cls and reg:
        return build_designation(base, cls, int(reg), execution=execution or None, doc_kind_code=None)
    m = _SPEC_BASE_RE.match(text)
    if m:
        return m.group(1).upper()
    for suffix in _ASSEMBLY_KIND_SUFFIXES:
        if text.upper().endswith(suffix):
            return text[: -len(suffix)]
    return text


def is_assembly_drawing(doc: BaseDocument) -> bool:
    dd = doc.design_document
    return bool(dd and (dd.doc_kind_code or "").upper() == "СБ")


async def find_specification_for_assembly(
    session: AsyncSession,
    assembly_doc: BaseDocument,
) -> BaseDocument | None:
    if assembly_doc.specification_document_id:
        linked = await session.get(BaseDocument, assembly_doc.specification_document_id)
        if linked and linked.is_specification:
            return linked

    result = await session.execute(
        select(BaseDocument)
        .options(joinedload(BaseDocument.design_document))
        .where(
            BaseDocument.is_specification.is_(True),
            BaseDocument.assembly_document_id == assembly_doc.id,
        )
        .limit(1)
    )
    found = result.scalars().first()
    if found:
        return found

    designation = get_document_designation(assembly_doc)
    base = strip_assembly_kind_suffix(designation)
    if not base:
        return None
    candidates = await search_specification_candidates(session, base)
    if len(candidates) == 1:
        return await session.get(BaseDocument, candidates[0]["id"])
    return None


async def search_specification_candidates(
    session: AsyncSession,
    assembly_designation: str,
    *,
    limit: int = 10,
) -> list[dict[str, Any]]:
    base = strip_assembly_kind_suffix(assembly_designation)
    if not base:
        return []

    result = await session.execute(
        select(BaseDocument)
        .options(joinedload(BaseDocument.design_document))
        .where(BaseDocument.is_specification.is_(True))
        .order_by(BaseDocument.id.desc())
        .limit(200)
    )
    docs = list(result.scalars().unique().all())
    out: list[dict[str, Any]] = []
    for doc in docs:
        des = get_document_designation(doc)
        if des.upper() == base.upper():
            out.append(
                {
                    "id": doc.id,
                    "designation": des,
                    "doc_name": doc.doc_name or "",
                    "score": 100,
                }
            )
    out.sort(key=lambda x: x["id"], reverse=True)
    return out[:limit]


async def link_specification_to_assembly(
    session: AsyncSession,
    spec_doc: BaseDocument,
    assembly_doc: BaseDocument,
    user: User,
) -> None:
    if not spec_doc.is_specification:
        raise HTTPException(status_code=400, detail="Выбранная запись не является спецификацией.")
    if not is_assembly_drawing(assembly_doc):
        raise HTTPException(status_code=400, detail="Привязка возможна только к сборочному чертежу (СБ).")
    if spec_doc.id == assembly_doc.id:
        raise HTTPException(status_code=400, detail="Нельзя привязать запись к самой себе.")

    if assembly_doc.specification_document_id and assembly_doc.specification_document_id != spec_doc.id:
        raise HTTPException(status_code=400, detail="У сборочного чертежа уже привязана другая спецификация.")
    if spec_doc.assembly_document_id and spec_doc.assembly_document_id != assembly_doc.id:
        raise HTTPException(status_code=400, detail="Спецификация уже привязана к другому сборочному чертежу.")

    spec_doc.assembly_document_id = assembly_doc.id
    assembly_doc.specification_document_id = spec_doc.id
    await session.flush()


def _normalize_section_name(text: str) -> str:
    cleaned = (text or "").strip()
    if not cleaned:
        return ""
    upper = cleaned.upper()
    for section in GOST_SPEC_SECTIONS:
        if section.upper() in upper or upper in section.upper():
            return section
    return cleaned


def parse_spec_rows_from_geometry(geometry: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not geometry:
        return []
    rows = geometry.get("spec_rows") or []
    out: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        out.append(
            {
                "section": _normalize_section_name(str(row.get("section") or "")),
                "position": str(row.get("position") or "").strip() or None,
                "row_format": str(row.get("format") or row.get("row_format") or "").strip() or None,
                "zone": str(row.get("zone") or "").strip() or None,
                "row_designation": str(row.get("designation") or row.get("row_designation") or "").strip() or None,
                "row_name": str(row.get("name") or row.get("row_name") or "").strip() or None,
                "quantity": str(row.get("quantity") or "").strip() or None,
                "note": str(row.get("note") or "").strip() or None,
                "sort_order": int(row.get("sort_order", index)),
                "bbox_norm": row.get("bbox_norm"),
            }
        )
    return out


async def match_designation_to_archive(
    session: AsyncSession,
    row_designation: str | None,
) -> tuple[int | None, float]:
    """Return (document_id, confidence 0-100) for a spec row designation."""
    token = (row_designation or "").strip().upper()
    if not token:
        return None, 0.0

    result = await session.execute(
        select(BaseDocument)
        .options(
            joinedload(BaseDocument.design_document),
            joinedload(BaseDocument.tech_document),
        )
        .order_by(BaseDocument.id.desc())
        .limit(500)
    )
    best_id: int | None = None
    best_score = 0.0
    for doc in result.scalars().unique().all():
        des = (get_document_designation(doc) or "").upper()
        if not des:
            continue
        if des == token:
            return doc.id, 100.0
        score = float(fuzz.ratio(des, token))
        if score > best_score:
            best_score = score
            best_id = doc.id
    if best_score >= _LINK_MATCH_THRESHOLD:
        return best_id, best_score
    return None, best_score


async def persist_specification_entries(
    session: AsyncSession,
    host_doc: BaseDocument,
    rows: list[dict[str, Any]],
    *,
    auto_link: bool = True,
    source: SpecificationEntrySource = SpecificationEntrySource.ocr,
) -> list[SpecificationEntry]:
    created: list[SpecificationEntry] = []
    for index, row in enumerate(rows):
        linked_id = row.get("linked_document_id")
        confidence = row.get("match_confidence")
        if auto_link and not linked_id:
            linked_id, confidence = await match_designation_to_archive(session, row.get("row_designation"))

        entry = SpecificationEntry(
            host_document_id=host_doc.id,
            section=row.get("section") or "",
            position=row.get("position"),
            row_format=row.get("row_format"),
            zone=row.get("zone"),
            row_designation=row.get("row_designation"),
            row_name=row.get("row_name"),
            quantity=row.get("quantity"),
            note=row.get("note"),
            linked_document_id=linked_id,
            match_confidence=str(int(confidence)) if confidence else None,
            source=source.value,
            sort_order=int(row.get("sort_order", index)),
        )
        session.add(entry)
        created.append(entry)
    await session.flush()
    return created


async def get_entries_grouped_by_section(
    session: AsyncSession,
    host_document_id: int,
) -> dict[str, list[SpecificationEntry]]:
    result = await session.execute(
        select(SpecificationEntry)
        .options(joinedload(SpecificationEntry.linked_document).joinedload(BaseDocument.design_document))
        .where(SpecificationEntry.host_document_id == host_document_id)
        .order_by(SpecificationEntry.section.asc(), SpecificationEntry.sort_order.asc(), SpecificationEntry.id.asc())
    )
    entries = list(result.scalars().unique().all())
    grouped: dict[str, list[SpecificationEntry]] = {}
    for entry in entries:
        section = entry.section or "Прочее"
        grouped.setdefault(section, []).append(entry)
    return grouped


async def create_auto_draft_from_spec_row(
    session: AsyncSession,
    *,
    host_doc: BaseDocument,
    row: dict[str, Any],
    user: User,
    org_id: int,
    class_code_id: int,
    org_code: str,
    class_code: str,
) -> BaseDocument | None:
    """Create archive record with auto_draft status when row designation not found."""
    row_des = (row.get("row_designation") or "").strip()
    if not row_des:
        return None

    parts = parse_designation_parts(row_des)
    kind = match_doc_kind_code(parts.get("doc_kind_code") or "") or parts.get("doc_kind_code")
    if kind and kind not in DOC_KIND_CODES:
        kind = None
    execution = parts.get("execution") or None

    from app.database import check_prni_unique, get_next_prni

    if parts.get("reg_number"):
        prni = int(parts["reg_number"])
    else:
        prni = await get_next_prni(
            session,
            org_id,
            class_code_id,
            org_code,
            class_code,
            execution=execution,
            doc_kind_code=kind,
        )

    designation = build_designation(
        parts.get("org_code") or org_code,
        parts.get("class_code") or class_code,
        prni,
        execution=execution,
        doc_kind_code=kind,
    )

    if not await check_prni_unique(
        session,
        org_id,
        class_code_id,
        prni,
        org_code,
        class_code,
        execution=execution,
        doc_kind_code=kind,
    ):
        return None

    draft = BaseDocument(
        type="DD",
        doc_name=(row.get("row_name") or "").strip() or None,
        developed_by=host_doc.developed_by,
        created_by=user.full_name,
        uploaded_by=user.id,
        position=user.position,
        department=user.department,
        project_id=host_doc.project_id,
        product_id=host_doc.product_id,
        status=DocumentStatus.auto_draft,
        document_format=row.get("row_format") or host_doc.document_format,
        auto_recognized=True,
    )
    session.add(draft)
    await session.flush()
    session.add(
        DesignDocument(
            id=draft.id,
            org_id=org_id,
            kd_class_code_id=class_code_id,
            prni=prni,
            designation=designation,
            org_code_str=org_code,
            class_code_str=class_code,
            execution=execution,
            doc_kind_code=kind,
        )
    )
    await session.flush()
    return draft


def build_dataset_spec_payload(geometry: dict[str, Any] | None, entries: list[SpecificationEntry] | None = None) -> dict[str, Any]:
    """Ground-truth fragment for ML dataset export."""
    geometry = geometry or {}
    payload = {
        "document_role": geometry.get("document_role"),
        "has_specification": geometry.get("has_specification"),
        "is_specification_document": geometry.get("is_specification_document"),
        "spec_page_indices": geometry.get("spec_page_indices") or [],
        "assembly_page_indices": geometry.get("assembly_page_indices") or [],
        "embedded_spec_pages": geometry.get("embedded_spec_pages") or [],
        "sections_found": geometry.get("sections_found") or [],
        "spec_rows": geometry.get("spec_rows") or [],
        "detection_confidence": geometry.get("detection_confidence"),
        "markers": geometry.get("markers") or {},
    }
    if entries:
        payload["specification_entries"] = [
            {
                "section": e.section,
                "position": e.position,
                "row_format": e.row_format,
                "zone": e.zone,
                "row_designation": e.row_designation,
                "row_name": e.row_name,
                "quantity": e.quantity,
                "note": e.note,
                "linked_document_id": e.linked_document_id,
                "match_confidence": e.match_confidence,
            }
            for e in entries
        ]
    return payload
