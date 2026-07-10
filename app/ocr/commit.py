"""Commit an OCR job into a governed document (DD/TD) + attach the staged file."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.change_log import log_change_event, log_file_upload
from app.database import (
    check_prn_unique,
    check_prni_unique,
    get_next_prn,
    get_next_prni,
    get_or_create_class_id,
    get_or_create_org_id,
)
from app.designation_helpers import build_designation, parse_execution_input
from app.document_format import is_valid_document_format
from app.document_helpers import resolve_document_storage_slugs, save_document_file_from_path
from app.models import (
    DOC_KIND_CODES,
    BaseDocument,
    DesignDocument,
    DocumentChangeEventType,
    DocumentStatus,
    OcrExtraction,
    OcrJob,
    OcrJobStatus,
    TechDocument,
    User,
)
from app.name_helpers import normalize_person_name
from app.notifications import get_document_designation, notify_file_upload
from app.ocr.service import field_value, latest_extraction
from app.product_helpers import create_product, validate_product_belongs_to_project
from app.project_helpers import create_new_project, get_project_by_id

_DESIGNATION_SERIAL = re.compile(
    r"^(\d{1,4})(?:-(\d{1,2}))?([A-Za-zА-Яа-яЁё0-9]{0,3})?$"
)


async def commit_ocr_job(
    session: AsyncSession,
    job: OcrJob,
    user: User,
    form: dict[str, Any],
) -> BaseDocument:
    if job.status == OcrJobStatus.committed:
        raise HTTPException(status_code=400, detail="Документ уже создан из этой задачи.")
    if job.status == OcrJobStatus.discarded:
        raise HTTPException(status_code=400, detail="Задача отклонена.")

    doc_type = (form.get("doc_type") or "").strip()
    org_code = (form.get("org_code") or "").strip()
    class_code = (form.get("class_code") or "").strip()
    reg_number = (form.get("reg_number") or "").strip()
    doc_name = (form.get("doc_name") or "").strip() or None
    developed_by = normalize_person_name(form.get("developed_by") or "")
    reviewed_by = normalize_person_name(form.get("reviewed_by") or "") or None
    approved_by = normalize_person_name(form.get("approved_by") or "") or None
    developer_signed_date = (form.get("developer_signed_date") or "").strip() or None
    reviewer_signed_date = (form.get("reviewer_signed_date") or "").strip() or None
    approver_signed_date = (form.get("approver_signed_date") or "").strip() or None
    is_okpo = form.get("is_okpo") == "true"
    org_name = (form.get("org_name") or "").strip() or None
    doc_kind_code = (form.get("doc_kind_code") or "").strip()
    execution_raw = (form.get("execution") or "").strip()
    document_format = (form.get("document_format") or "").strip()
    existing_project_id = (form.get("existing_project_id") or "").strip()
    existing_product_id = (form.get("existing_product_id") or "").strip()
    new_project_name = (form.get("new_project_name") or "").strip()
    new_project_cipher = (form.get("new_project_cipher") or "").strip()
    new_product_name = (form.get("new_product_name") or "").strip()

    if not developed_by:
        raise HTTPException(status_code=400, detail="Необходимо указать ФИО разработчика.")
    if doc_type not in ("DD", "TD"):
        raise HTTPException(status_code=400, detail="Неверный тип документа.")
    if not all([org_code, class_code]):
        raise HTTPException(status_code=400, detail="Код организации и код классификации обязательны.")
    if doc_kind_code and doc_kind_code not in DOC_KIND_CODES:
        raise HTTPException(status_code=400, detail="Неверный код вида документа.")
    if not document_format or not is_valid_document_format(document_format):
        raise HTTPException(status_code=400, detail="Укажите корректный формат листа.")

    is_kd = doc_type == "DD"
    execution = parse_execution_input(execution_raw) if is_kd else None
    if not is_kd and execution_raw:
        raise HTTPException(status_code=400, detail="Исполнение доступно только для конструкторской документации.")

    if existing_project_id and new_project_name:
        raise HTTPException(status_code=400, detail="Выберите существующий проект или укажите новый, но не оба сразу.")
    product = None
    if existing_project_id:
        project = await get_project_by_id(session, int(existing_project_id))
        if not existing_product_id:
            raise HTTPException(status_code=400, detail="Необходимо выбрать изделие.")
        product = await validate_product_belongs_to_project(session, int(existing_product_id), project.id)
    elif new_project_name:
        project = await create_new_project(session, new_project_name, new_project_cipher)
        if not new_product_name:
            raise HTTPException(
                status_code=400,
                detail="При создании нового проекта укажите наименование первого изделия.",
            )
        product = await create_product(session, project, new_product_name)
    else:
        raise HTTPException(status_code=400, detail="Необходимо выбрать или указать проект.")

    base_doc = BaseDocument(
        type=doc_type,
        doc_name=doc_name,
        developed_by=developed_by,
        reviewed_by=reviewed_by,
        approved_by=approved_by,
        developer_signed_date=developer_signed_date,
        reviewer_signed_date=reviewer_signed_date,
        approver_signed_date=approver_signed_date,
        created_by=user.full_name,
        uploaded_by=user.id,
        position=user.position,
        department=user.department,
        project_id=project.id,
        product_id=product.id,
        status=DocumentStatus.pending_review,
        document_format=document_format,
    )
    session.add(base_doc)
    await session.flush()

    extraction = latest_extraction(job)
    await log_change_event(
        session,
        base_doc,
        user,
        DocumentChangeEventType.register,
        comment="Регистрация записи из OCR",
        payload={
            "ocr_job_id": job.id,
            "ocr_batch_id": job.batch_id,
            "pipeline_version": job.pipeline_version,
            "ocr_fields": (extraction.fields if extraction else None),
        },
    )

    org_id = await get_or_create_org_id(session, org_code, is_okpo=is_okpo, org_name=org_name)
    class_code_id = await get_or_create_class_id(session, class_code, is_kd=is_kd)

    if is_kd:
        if reg_number:
            prni_to_save = int(reg_number)
            if not await check_prni_unique(
                session,
                org_id,
                class_code_id,
                prni_to_save,
                org_code,
                class_code,
                execution=execution,
                doc_kind_code=doc_kind_code or None,
            ):
                raise HTTPException(status_code=400, detail="Указанное обозначение уже используется.")
        else:
            prni_to_save = await get_next_prni(
                session,
                org_id,
                class_code_id,
                org_code,
                class_code,
                execution=execution,
                doc_kind_code=doc_kind_code or None,
            )
        designation = build_designation(
            org_code,
            class_code,
            prni_to_save,
            execution=execution,
            doc_kind_code=doc_kind_code or None,
        )
        session.add(
            DesignDocument(
                id=base_doc.id,
                org_id=org_id,
                kd_class_code_id=class_code_id,
                prni=prni_to_save,
                designation=designation,
                org_code_str=org_code,
                class_code_str=class_code,
                execution=execution,
                doc_kind_code=doc_kind_code or None,
            )
        )
    else:
        if reg_number:
            prn_to_save = int(reg_number)
            if not await check_prn_unique(
                session,
                org_id,
                class_code_id,
                prn_to_save,
                org_code,
                class_code,
            ):
                raise HTTPException(status_code=400, detail="Указанное обозначение уже используется.")
        else:
            prn_to_save = await get_next_prn(session, org_id, class_code_id, org_code, class_code)
        designation = build_designation(org_code, class_code, prn_to_save)
        session.add(
            TechDocument(
                id=base_doc.id,
                org_id=org_id,
                td_class_code_id=class_code_id,
                prn=prn_to_save,
                designation=designation,
                org_code_str=org_code,
                class_code_str=class_code,
            )
        )

    await session.flush()
    await session.refresh(base_doc, ["design_document", "tech_document", "project", "product"])

    project_slug, product_slug = resolve_document_storage_slugs(base_doc)
    designation = get_document_designation(base_doc)
    file_path, stored_name = save_document_file_from_path(
        job.stored_path,
        job.original_filename,
        project_slug,
        product_slug=product_slug,
        doc_kind_code=base_doc.design_document.doc_kind_code if base_doc.design_document else None,
        designation=designation,
        doc_name=doc_name,
    )

    base_doc.file_path = file_path
    base_doc.file_name = stored_name
    if not base_doc.registration_notified_at:
        base_doc.registration_notified_at = datetime.utcnow()

    await log_file_upload(session, base_doc, user, stored_name, replacement=False)
    await notify_file_upload(
        session,
        base_doc,
        user,
        had_file_before=False,
        registration_already_notified=False,
    )

    if extraction:
        session.add(
            OcrExtraction(
                job_id=job.id,
                source="corrected",
                fields=_fields_from_form(form, extraction.fields or {}),
                geometry=extraction.geometry or {},
                stamp_crop_path=extraction.stamp_crop_path,
                page_preview_path=extraction.page_preview_path,
                person_suggestions=extraction.person_suggestions,
                created_at=datetime.utcnow(),
            )
        )

    job.status = OcrJobStatus.committed
    job.document_id = base_doc.id
    job.finished_at = datetime.utcnow()
    job.error_message = None

    await session.commit()
    await session.refresh(base_doc)
    return base_doc


def _fields_from_form(form: dict[str, Any], previous: dict) -> dict:
    result = dict(previous) if previous else {}
    mapping = {
        "doc_name": form.get("doc_name"),
        "developed_by": form.get("developed_by"),
        "reviewed_by": form.get("reviewed_by"),
        "approved_by": form.get("approved_by"),
        "developer_signed_date": form.get("developer_signed_date"),
        "reviewer_signed_date": form.get("reviewer_signed_date"),
        "approver_signed_date": form.get("approver_signed_date"),
        "document_format": form.get("document_format"),
    }
    org = (form.get("org_code") or "").strip()
    cls = (form.get("class_code") or "").strip()
    reg = (form.get("reg_number") or "").strip()
    execution = (form.get("execution") or "").strip()
    kind = (form.get("doc_kind_code") or "").strip()
    if org and cls:
        if reg:
            designation = f"{org}.{cls}.{reg.zfill(3)}"
            if execution:
                designation += f"-{execution.zfill(2)}"
            if kind:
                designation += kind
        else:
            designation = f"{org}.{cls}"
        mapping["designation"] = designation

    for key, value in mapping.items():
        text = (value or "").strip() if isinstance(value, str) else (str(value).strip() if value else "")
        prev = result.get(key) or {}
        result[key] = {
            "raw": prev.get("raw"),
            "value": text or None,
            "conf": prev.get("conf"),
            "bbox": prev.get("bbox"),
            "page": prev.get("page", 0),
        }
    return result


async def discard_job(session: AsyncSession, job: OcrJob) -> None:
    if job.status == OcrJobStatus.committed:
        raise HTTPException(status_code=400, detail="Нельзя отклонить задачу с созданным документом.")
    job.status = OcrJobStatus.discarded
    job.finished_at = datetime.utcnow()
    await session.commit()


def prefill_from_extraction(extraction: OcrExtraction | None) -> dict[str, str]:
    fields = extraction.fields if extraction else {}
    geometry = extraction.geometry if extraction else {}
    fmt = field_value(fields, "document_format") or (geometry or {}).get("format_from_dims") or ""
    designation = field_value(fields, "designation")
    org_code = class_code = reg_number = execution = doc_kind_code = ""
    if designation:
        parts = designation.replace(" ", "").split(".")
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

    return {
        "org_code": org_code,
        "class_code": class_code,
        "reg_number": reg_number,
        "execution": execution,
        "doc_kind_code": doc_kind_code,
        "doc_name": field_value(fields, "doc_name"),
        "developed_by": field_value(fields, "developed_by"),
        "reviewed_by": field_value(fields, "reviewed_by"),
        "approved_by": field_value(fields, "approved_by"),
        "developer_signed_date": field_value(fields, "developer_signed_date"),
        "reviewer_signed_date": field_value(fields, "reviewer_signed_date"),
        "approver_signed_date": field_value(fields, "approver_signed_date"),
        "document_format": fmt if isinstance(fmt, str) else "",
    }
