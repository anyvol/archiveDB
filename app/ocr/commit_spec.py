"""OCR commit paths for specifications and SB split."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.change_log import log_change_event, log_file_upload
from app.database import (
    check_prni_unique,
    get_next_prni,
    get_or_create_class_id,
    get_or_create_org_id,
)
from app.designation_helpers import build_designation
from app.document_applicability import add_document_applicability_many
from app.document_helpers import resolve_document_storage_slugs, save_document_file_from_path
from app.models import (
    BaseDocument,
    DesignDocument,
    DocumentChangeEventType,
    DocumentStatus,
    OcrExtraction,
    OcrJob,
    OcrJobStatus,
    User,
)
from app.notifications import get_document_designation, notify_file_upload
from app.ocr.split import split_source_file
from app.specification_helpers import (
    link_specification_to_assembly,
    parse_spec_rows_from_geometry,
    persist_specification_entries,
    strip_assembly_kind_suffix,
    create_auto_draft_from_spec_row,
)


@dataclass
class OcrCommitResult:
    primary: BaseDocument
    secondary: BaseDocument | None = None
    message: str | None = None


def _rows_from_form(form: dict[str, Any], geometry: dict[str, Any]) -> list[dict[str, Any]]:
    raw = form.get("spec_rows_json")
    if raw:
        try:
            parsed = json.loads(raw) if isinstance(raw, str) else raw
            if isinstance(parsed, list):
                return parsed
        except json.JSONDecodeError:
            pass
    return parse_spec_rows_from_geometry(geometry)


async def _create_kd_document_core(
    session: AsyncSession,
    *,
    user: User,
    project_id: int,
    product_id: int,
    doc_name: str | None,
    developed_by: str,
    reviewed_by: str | None,
    approved_by: str | None,
    developer_signed_date: str | None,
    reviewer_signed_date: str | None,
    approver_signed_date: str | None,
    has_developer_signature: bool,
    has_reviewer_signature: bool,
    has_approver_signature: bool,
    document_format: str,
    org_id: int,
    class_code_id: int,
    org_code: str,
    class_code: str,
    prni: int,
    execution: str | None,
    doc_kind_code: str | None,
    is_specification: bool = False,
    contains_embedded_specification: bool = False,
) -> BaseDocument:
    base_doc = BaseDocument(
        type="DD",
        doc_name=doc_name,
        developed_by=developed_by,
        reviewed_by=reviewed_by,
        approved_by=approved_by,
        developer_signed_date=developer_signed_date,
        reviewer_signed_date=reviewer_signed_date,
        approver_signed_date=approver_signed_date,
        has_developer_signature=has_developer_signature,
        has_reviewer_signature=has_reviewer_signature,
        has_approver_signature=has_approver_signature,
        created_by=user.full_name,
        uploaded_by=user.id,
        position=user.position,
        department=user.department,
        project_id=project_id,
        product_id=product_id,
        status=DocumentStatus.pending_review,
        document_format=document_format,
        auto_recognized=True,
        is_specification=is_specification,
        contains_embedded_specification=contains_embedded_specification,
    )
    session.add(base_doc)
    await session.flush()
    designation = build_designation(
        org_code,
        class_code,
        prni,
        execution=execution,
        doc_kind_code=doc_kind_code if not is_specification else None,
    )
    session.add(
        DesignDocument(
            id=base_doc.id,
            org_id=org_id,
            kd_class_code_id=class_code_id,
            prni=prni,
            designation=designation,
            org_code_str=org_code,
            class_code_str=class_code,
            execution=execution,
            doc_kind_code=doc_kind_code if not is_specification else None,
        )
    )
    await session.flush()
    await session.refresh(base_doc, ["design_document", "project", "product"])
    return base_doc


async def _attach_file(
    session: AsyncSession,
    base_doc: BaseDocument,
    source_path: str,
    original_filename: str,
    user: User,
    *,
    is_specification: bool = False,
) -> None:
    project_slug, product_slug = resolve_document_storage_slugs(base_doc)
    designation = get_document_designation(base_doc)
    file_path, stored_name = save_document_file_from_path(
        source_path,
        original_filename,
        project_slug,
        product_slug=product_slug,
        doc_kind_code=base_doc.design_document.doc_kind_code if base_doc.design_document else None,
        is_specification=is_specification,
        designation=designation,
        doc_name=base_doc.doc_name,
    )
    base_doc.file_path = file_path
    base_doc.file_name = stored_name
    if not base_doc.registration_notified_at:
        base_doc.registration_notified_at = datetime.utcnow()
    await log_file_upload(session, base_doc, user, stored_name, replacement=False)


async def _finalize_spec_rows(
    session: AsyncSession,
    host_doc: BaseDocument,
    rows: list[dict[str, Any]],
    user: User,
    *,
    org_id: int,
    class_code_id: int,
    org_code: str,
    class_code: str,
    auto_create_drafts: bool,
) -> list[BaseDocument]:
    drafts: list[BaseDocument] = []
    entries = await persist_specification_entries(session, host_doc, rows, auto_link=True)
    if not auto_create_drafts:
        return drafts
    for entry, row in zip(entries, rows):
        if entry.linked_document_id:
            continue
        draft = await create_auto_draft_from_spec_row(
            session,
            host_doc=host_doc,
            row=row,
            user=user,
            org_id=org_id,
            class_code_id=class_code_id,
            org_code=org_code,
            class_code=class_code,
        )
        if draft:
            entry.linked_document_id = draft.id
            drafts.append(draft)
    await session.flush()
    return drafts


async def commit_with_specification(
    session: AsyncSession,
    job: OcrJob,
    user: User,
    form: dict[str, Any],
    *,
    extraction: OcrExtraction | None,
    geometry: dict[str, Any],
    org_id: int,
    class_code_id: int,
    org_code: str,
    class_code: str,
    prni: int,
    execution: str | None,
    doc_kind_code: str,
    project_id: int,
    product_id: int,
    doc_name: str | None,
    developed_by: str,
    reviewed_by: str | None,
    approved_by: str | None,
    developer_signed_date: str | None,
    reviewer_signed_date: str | None,
    approver_signed_date: str | None,
    has_developer_signature: bool,
    has_reviewer_signature: bool,
    has_approver_signature: bool,
    document_format: str,
    extra_product_ids: list[int],
) -> OcrCommitResult:
    role = geometry.get("document_role") or "assembly_drawing"
    rows = _rows_from_form(form, geometry)
    auto_create = form.get("auto_create_spec_rows") != "false"

    if role == "standalone_specification":
        spec_doc = await _create_kd_document_core(
            session,
            user=user,
            project_id=project_id,
            product_id=product_id,
            doc_name=doc_name,
            developed_by=developed_by,
            reviewed_by=reviewed_by,
            approved_by=approved_by,
            developer_signed_date=developer_signed_date,
            reviewer_signed_date=reviewer_signed_date,
            approver_signed_date=approver_signed_date,
            has_developer_signature=has_developer_signature,
            has_reviewer_signature=has_reviewer_signature,
            has_approver_signature=has_approver_signature,
            document_format=document_format,
            org_id=org_id,
            class_code_id=class_code_id,
            org_code=org_code,
            class_code=class_code,
            prni=prni,
            execution=execution,
            doc_kind_code=None,
            is_specification=True,
        )
        await log_change_event(
            session,
            spec_doc,
            user,
            DocumentChangeEventType.register,
            comment="Регистрация спецификации из OCR",
        )
        await _attach_file(session, spec_doc, job.stored_path, job.original_filename, user, is_specification=True)
        await _finalize_spec_rows(
            session, spec_doc, rows, user,
            org_id=org_id, class_code_id=class_code_id, org_code=org_code, class_code=class_code,
            auto_create_drafts=auto_create,
        )
        job.status = OcrJobStatus.committed
        job.document_id = spec_doc.id
        job.finished_at = datetime.utcnow()
        await session.commit()
        return OcrCommitResult(primary=spec_doc, message="Создана запись спецификации.")

    paths = split_source_file(job.stored_path, geometry)
    assembly_path = paths["assembly"] or job.stored_path
    spec_path = paths["specification"]

    if role == "combined_a4":
        sb_doc = await _create_kd_document_core(
            session,
            user=user,
            project_id=project_id,
            product_id=product_id,
            doc_name=doc_name,
            developed_by=developed_by,
            reviewed_by=reviewed_by,
            approved_by=approved_by,
            developer_signed_date=developer_signed_date,
            reviewer_signed_date=reviewer_signed_date,
            approver_signed_date=approver_signed_date,
            has_developer_signature=has_developer_signature,
            has_reviewer_signature=has_reviewer_signature,
            has_approver_signature=has_approver_signature,
            document_format=document_format,
            org_id=org_id,
            class_code_id=class_code_id,
            org_code=org_code,
            class_code=class_code,
            prni=prni,
            execution=execution,
            doc_kind_code=doc_kind_code or "СБ",
            contains_embedded_specification=True,
        )
        await log_change_event(
            session,
            sb_doc,
            user,
            DocumentChangeEventType.register,
            comment="Регистрация СБ со спецификацией на листе (OCR)",
        )
        await _attach_file(session, sb_doc, assembly_path, job.original_filename, user)
        await _finalize_spec_rows(
            session, sb_doc, rows, user,
            org_id=org_id, class_code_id=class_code_id, org_code=org_code, class_code=class_code,
            auto_create_drafts=auto_create,
        )
        if extra_product_ids:
            await add_document_applicability_many(session, sb_doc, extra_product_ids, user)
        await notify_file_upload(session, sb_doc, user, had_file_before=False, registration_already_notified=False)
        job.status = OcrJobStatus.committed
        job.document_id = sb_doc.id
        job.finished_at = datetime.utcnow()
        await session.commit()
        sb_des = get_document_designation(sb_doc)
        return OcrCommitResult(
            primary=sb_doc,
            message=f"Создана запись СБ {sb_des} со спецификацией на листе.",
        )

    if role == "assembly_with_spec_pages" and spec_path:
        sb_doc = await _create_kd_document_core(
            session,
            user=user,
            project_id=project_id,
            product_id=product_id,
            doc_name=doc_name,
            developed_by=developed_by,
            reviewed_by=reviewed_by,
            approved_by=approved_by,
            developer_signed_date=developer_signed_date,
            reviewer_signed_date=reviewer_signed_date,
            approver_signed_date=approver_signed_date,
            has_developer_signature=has_developer_signature,
            has_reviewer_signature=has_reviewer_signature,
            has_approver_signature=has_approver_signature,
            document_format=document_format,
            org_id=org_id,
            class_code_id=class_code_id,
            org_code=org_code,
            class_code=class_code,
            prni=prni,
            execution=execution,
            doc_kind_code=doc_kind_code or "СБ",
        )
        spec_prni = prni
        if not await check_prni_unique(
            session, org_id, class_code_id, spec_prni, org_code, class_code,
            execution=execution, doc_kind_code=None,
        ):
            spec_prni = await get_next_prni(
                session, org_id, class_code_id, org_code, class_code,
                execution=execution, doc_kind_code=None,
            )
        spec_doc = await _create_kd_document_core(
            session,
            user=user,
            project_id=project_id,
            product_id=product_id,
            doc_name=doc_name,
            developed_by=developed_by,
            reviewed_by=reviewed_by,
            approved_by=approved_by,
            developer_signed_date=developer_signed_date,
            reviewer_signed_date=reviewer_signed_date,
            approver_signed_date=approver_signed_date,
            has_developer_signature=has_developer_signature,
            has_reviewer_signature=has_reviewer_signature,
            has_approver_signature=has_approver_signature,
            document_format=document_format,
            org_id=org_id,
            class_code_id=class_code_id,
            org_code=org_code,
            class_code=class_code,
            prni=spec_prni,
            execution=execution,
            doc_kind_code=None,
            is_specification=True,
        )
        await link_specification_to_assembly(session, spec_doc, sb_doc, user)
        await log_change_event(session, sb_doc, user, DocumentChangeEventType.register, comment="Регистрация СБ из OCR (split)")
        await log_change_event(session, spec_doc, user, DocumentChangeEventType.register, comment="Регистрация спецификации из OCR (split)")
        await _attach_file(session, sb_doc, assembly_path, job.original_filename, user)
        await _attach_file(session, spec_doc, spec_path, job.original_filename, user, is_specification=True)
        await _finalize_spec_rows(
            session, spec_doc, rows, user,
            org_id=org_id, class_code_id=class_code_id, org_code=org_code, class_code=class_code,
            auto_create_drafts=auto_create,
        )
        if extra_product_ids:
            await add_document_applicability_many(session, sb_doc, extra_product_ids, user)
        await notify_file_upload(session, sb_doc, user, had_file_before=False, registration_already_notified=False)
        await notify_file_upload(session, spec_doc, user, had_file_before=False, registration_already_notified=False)
        job.status = OcrJobStatus.committed
        job.document_id = sb_doc.id
        job.finished_at = datetime.utcnow()
        await session.commit()
        sb_des = get_document_designation(sb_doc)
        spec_des = get_document_designation(spec_doc)
        return OcrCommitResult(
            primary=sb_doc,
            secondary=spec_doc,
            message=f"Созданы записи: СБ {sb_des} и спецификация {spec_des}.",
        )

    raise HTTPException(status_code=400, detail="Не удалось определить сценарий сохранения спецификации.")
