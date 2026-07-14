"""Commit an OCR job into a governed document (DD/TD) + attach the staged file."""

from __future__ import annotations

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
from app.document_applicability import add_document_applicability_many
from app.document_format import is_valid_document_format
from app.document_helpers import resolve_document_storage_slugs, save_document_file_from_path
from app.document_links import add_document_links
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
from app.ocr.normalize import (
    coerce_document_format,
    date_hint_from_field,
    normalize_ocr_date,
    parse_bool_flag,
    parse_designation_parts,
)
from app.ocr.service import field_value, latest_extraction
from app.product_helpers import validate_product_belongs_to_project
from app.project_helpers import get_project_by_id
from app.ocr.commit_spec import OcrCommitResult, commit_with_specification


def _form_int_list(form: dict[str, Any], key: str) -> list[int]:
    raw = form.get(key)
    if raw is None:
        return []
    items = raw if isinstance(raw, list) else [raw]
    ids: list[int] = []
    for item in items:
        text = str(item).strip()
        if text.isdigit():
            ids.append(int(text))
    return ids


def _form_bool(form: dict[str, Any], key: str) -> bool | None:
    """Checkbox: present → True; explicit false string → False; missing → None."""
    if key not in form:
        return None
    raw = form.get(key)
    if isinstance(raw, list):
        raw = raw[-1] if raw else None
    parsed = parse_bool_flag(raw)
    if parsed is not None:
        return parsed
    # HTML checkbox sends "true" when checked; absent when unchecked — caller may pass ""
    return bool(raw) if raw not in (None, "") else False


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
    developer_signed_date = normalize_ocr_date(form.get("developer_signed_date") or "") or None
    reviewer_signed_date = normalize_ocr_date(form.get("reviewer_signed_date") or "") or None
    approver_signed_date = normalize_ocr_date(form.get("approver_signed_date") or "") or None
    is_okpo = form.get("is_okpo") == "true"
    org_name = (form.get("org_name") or "").strip() or None
    doc_kind_code = (form.get("doc_kind_code") or "").strip()
    execution_raw = (form.get("execution") or "").strip()
    document_format = coerce_document_format(form.get("document_format") or "")
    existing_project_id = (form.get("existing_project_id") or "").strip()
    existing_product_id = (form.get("existing_product_id") or "").strip()
    additional_product_ids = _form_int_list(form, "additional_product_ids")
    link_target_ids = _form_int_list(form, "link_target_ids")

    has_developer_signature = _form_bool(form, "has_developer_signature")
    has_reviewer_signature = _form_bool(form, "has_reviewer_signature")
    has_approver_signature = _form_bool(form, "has_approver_signature")
    # Unchecked checkboxes are omitted from form posts — treat as False when key missing
    if "has_developer_signature" not in form:
        has_developer_signature = False
    if "has_reviewer_signature" not in form:
        has_reviewer_signature = False
    if "has_approver_signature" not in form:
        has_approver_signature = False

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

    if not existing_project_id:
        raise HTTPException(
            status_code=400,
            detail="Выберите существующий проект. Новый проект создаётся в разделе «Проекты».",
        )
    if not existing_product_id:
        raise HTTPException(status_code=400, detail="Необходимо выбрать изделие.")
    project = await get_project_by_id(session, int(existing_project_id))
    product = await validate_product_belongs_to_project(session, int(existing_product_id), project.id)

    extra_product_ids = [pid for pid in additional_product_ids if pid != product.id]
    if extra_product_ids:
        for product_id in extra_product_ids:
            await validate_product_belongs_to_project(session, product_id, project.id)

    unique_link_ids: list[int] = []
    seen_links: set[int] = set()
    for target_id in link_target_ids:
        if target_id in seen_links:
            continue
        seen_links.add(target_id)
        unique_link_ids.append(target_id)

    extraction = latest_extraction(job)
    geometry = dict((extraction.geometry if extraction else {}) or {})
    document_role = geometry.get("document_role")
    if geometry.get("has_specification") and document_role in (
        "standalone_specification",
        "combined_a4",
        "assembly_with_spec_pages",
    ):
        org_id = await get_or_create_org_id(session, org_code, is_okpo=is_okpo, org_name=org_name)
        class_code_id = await get_or_create_class_id(session, class_code, is_kd=is_kd)
        if is_kd:
            if reg_number:
                prni_to_save = int(reg_number)
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
        else:
            raise HTTPException(status_code=400, detail="Спецификация поддерживается только для КД.")
        spec_result = await commit_with_specification(
            session,
            job,
            user,
            form,
            extraction=extraction,
            geometry=geometry,
            org_id=org_id,
            class_code_id=class_code_id,
            org_code=org_code,
            class_code=class_code,
            prni=prni_to_save,
            execution=execution,
            doc_kind_code=doc_kind_code or "СБ",
            project_id=project.id,
            product_id=product.id,
            doc_name=doc_name,
            developed_by=developed_by,
            reviewed_by=reviewed_by,
            approved_by=approved_by,
            developer_signed_date=developer_signed_date,
            reviewer_signed_date=reviewer_signed_date,
            approver_signed_date=approver_signed_date,
            has_developer_signature=bool(has_developer_signature),
            has_reviewer_signature=bool(has_reviewer_signature),
            has_approver_signature=bool(has_approver_signature),
            document_format=document_format,
            extra_product_ids=extra_product_ids,
        )
        setattr(spec_result.primary, "_ocr_commit_result", spec_result)
        return spec_result.primary

    base_doc = BaseDocument(
        type=doc_type,
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
        project_id=project.id,
        product_id=product.id,
        status=DocumentStatus.pending_review,
        document_format=document_format,
        auto_recognized=True,
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

    if extra_product_ids:
        await add_document_applicability_many(session, base_doc, extra_product_ids, user)

    if unique_link_ids:
        await add_document_links(session, base_doc, unique_link_ids, user)

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


async def discard_job(session: AsyncSession, job: OcrJob, user: User | None = None) -> None:
    """Mark job discarded but keep annotations and format-bound ROI templates."""
    if job.status == OcrJobStatus.committed:
        raise HTTPException(status_code=400, detail="Нельзя отклонить задачу с созданным документом.")

    # Persist ROI template for this paper format even when the job is rejected
    from app.ocr.annotate import (
        latest_annotation,
        resolve_document_format,
        upsert_format_template,
    )

    extraction = latest_extraction(job)
    annotation = await latest_annotation(session, job.id)
    if annotation and annotation.labels and annotation.labels.get("cells"):
        fmt = resolve_document_format(extraction, annotation.labels)
        if fmt and user is not None:
            await upsert_format_template(
                session,
                document_format=fmt,
                labels=annotation.labels,
                user=user,
            )
        elif fmt and annotation.labels.get("document_format") != fmt:
            labels = dict(annotation.labels)
            labels["document_format"] = fmt
            annotation.labels = labels

    job.status = OcrJobStatus.discarded
    job.finished_at = datetime.utcnow()
    await session.commit()


async def save_training_example(
    session: AsyncSession,
    job: OcrJob,
    user: User,
    form: dict[str, Any],
) -> OcrExtraction:
    """Save human-corrected fields as a training/ground-truth extraction without creating a document.

    Also upserts the format-bound ROI template when cell annotation exists.
    This feeds phase-3 dataset export; format templates already improve the next OCR runs.
    """
    if job.status == OcrJobStatus.committed:
        raise HTTPException(status_code=400, detail="Документ уже создан из этой задачи.")
    if job.status == OcrJobStatus.discarded:
        raise HTTPException(status_code=400, detail="Задача отклонена — учебный пример не сохранить.")

    from app.ocr.annotate import (
        latest_annotation,
        resolve_document_format,
        upsert_format_template,
    )

    extraction = latest_extraction(job)
    prev_fields = (extraction.fields if extraction else {}) or {}
    fields = _fields_from_form(form, prev_fields)

    # Attach signature flags into fields for export
    for form_key, field_key in (
        ("has_developer_signature", "developer_signature"),
        ("has_reviewer_signature", "reviewer_signature"),
        ("has_approver_signature", "approver_signature"),
    ):
        flag = parse_bool_flag(form.get(form_key))
        if form_key not in form:
            flag = False
        prev = fields.get(field_key) or {}
        fields[field_key] = {
            "raw": prev.get("raw"),
            "value": "true" if flag else "false",
            "conf": 1.0,
            "bbox": prev.get("bbox"),
            "page": prev.get("page", 0),
        }

    geometry = dict((extraction.geometry if extraction else {}) or {})
    fmt = coerce_document_format(form.get("document_format")) or resolve_document_format(extraction)
    if fmt:
        geometry["format_from_dims"] = geometry.get("format_from_dims") or fmt
        fields["document_format"] = {
            "raw": fields.get("document_format", {}).get("raw") or fmt,
            "value": fmt,
            "conf": 1.0,
            "bbox": (fields.get("document_format") or {}).get("bbox"),
            "page": 0,
        }

    annotation = await latest_annotation(session, job.id)
    if annotation and annotation.labels and annotation.labels.get("cells") and fmt:
        await upsert_format_template(
            session,
            document_format=fmt,
            labels={**annotation.labels, "document_format": fmt},
            user=user,
        )
        geometry["annotation_id"] = annotation.id
        geometry["format_template"] = fmt

    geometry["training"] = True
    geometry["labeled_by_user_id"] = user.id

    new_extraction = OcrExtraction(
        job_id=job.id,
        source="training",
        fields=fields,
        geometry=geometry,
        stamp_crop_path=extraction.stamp_crop_path if extraction else None,
        page_preview_path=extraction.page_preview_path if extraction else None,
        person_suggestions=extraction.person_suggestions if extraction else None,
        created_at=datetime.utcnow(),
    )
    session.add(new_extraction)
    job.status = OcrJobStatus.labeled
    job.finished_at = datetime.utcnow()
    job.error_message = None
    await session.commit()
    await session.refresh(new_extraction)
    return new_extraction


def prefill_from_extraction(extraction: OcrExtraction | None) -> dict[str, str]:
    fields = extraction.fields if extraction else {}
    geometry = extraction.geometry if extraction else {}
    fmt = (
        coerce_document_format(field_value(fields, "document_format"))
        or coerce_document_format((geometry or {}).get("format_from_dims"))
        or ""
    )
    designation = field_value(fields, "designation")
    parts = parse_designation_parts(designation)
    if not parts["doc_kind_code"]:
        raw_des = ((fields or {}).get("designation") or {}).get("raw") or ""
        if raw_des:
            parts["doc_kind_code"] = parse_designation_parts(str(raw_des))["doc_kind_code"]

    def _sig(key: str) -> str:
        flag = parse_bool_flag(field_value(fields, key))
        return "true" if flag else ""

    def _date(key: str) -> str:
        entry = (fields or {}).get(key) or {}
        return (
            normalize_ocr_date(entry.get("value"))
            or normalize_ocr_date(entry.get("raw"))
            or normalize_ocr_date(field_value(fields, key))
        )

    return {
        "org_code": parts["org_code"],
        "class_code": parts["class_code"],
        "reg_number": parts["reg_number"],
        "execution": parts["execution"],
        "doc_kind_code": parts["doc_kind_code"],
        "doc_name": field_value(fields, "doc_name"),
        "developed_by": field_value(fields, "developed_by"),
        "reviewed_by": field_value(fields, "reviewed_by"),
        "approved_by": field_value(fields, "approved_by"),
        "developer_signed_date": _date("developer_signed_date"),
        "reviewer_signed_date": _date("reviewer_signed_date"),
        "approver_signed_date": _date("approver_signed_date"),
        "document_format": fmt,
        "has_developer_signature": _sig("developer_signature"),
        "has_reviewer_signature": _sig("reviewer_signature"),
        "has_approver_signature": _sig("approver_signature"),
    }


def date_hints_from_extraction(extraction: OcrExtraction | None) -> dict[str, dict[str, str]]:
    fields = (extraction.fields if extraction else {}) or {}
    keys = ("developer_signed_date", "reviewer_signed_date", "approver_signed_date")
    return {k: date_hint_from_field(fields.get(k)) for k in keys}
