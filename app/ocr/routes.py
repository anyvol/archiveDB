"""OCR web and API routes (phase 1A/1B)."""

from __future__ import annotations

import io
import os
from urllib.parse import quote

from fastapi import APIRouter, Cookie, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.config import OCR_ALLOWED_EXTENSIONS, OCR_LOW_CONF_THRESHOLD, SERVICE_VERSION, UPLOAD_DIR, url_path
from app.database import get_session
from app.document_format import DOCUMENT_FORMATS, DOCUMENT_FORMAT_LABELS
from app.models import DOC_KIND_CODES, OCR_JOB_STATUS_LABELS, OcrJobStatus, Project
from app.name_helpers import fetch_known_org_codes, fetch_known_person_names, suggest_org_codes
from app.ocr.annotate import (
    FIELD_KEY_LABELS,
    annotation_bootstrap,
    latest_annotation,
    reocr_from_annotation,
    save_annotation,
)
from app.ocr.commit import (
    commit_ocr_job,
    date_hints_from_extraction,
    discard_job,
    prefill_from_extraction,
    save_training_example,
)
from app.ocr.dataset import build_dataset_zip, dataset_stats
from app.ocr.service import (
    _build_field_suggestions,
    create_batch_with_files,
    field_confidence,
    get_batch,
    get_job,
    latest_extraction,
    ocr_service_available,
    retry_job,
)
from app.permissions import can_add_document_links, can_create_document, is_admin, is_master_admin
from app.session_helpers import resolve_authenticated_user, wants_json_response

router = APIRouter(tags=["ocr"])
templates = Jinja2Templates(directory="templates")
templates.env.globals["url_path"] = url_path
templates.env.globals["DOCUMENT_FORMATS"] = DOCUMENT_FORMATS
templates.env.globals["DOCUMENT_FORMAT_LABELS"] = DOCUMENT_FORMAT_LABELS
templates.env.globals["DOC_KIND_CODES"] = DOC_KIND_CODES
templates.env.globals["OCR_JOB_STATUS_LABELS"] = OCR_JOB_STATUS_LABELS


def _field_rois_for_review(fields: dict) -> list[dict]:
    """Ordered ROI snippets metadata for the review page (client crops from stamp image)."""
    out: list[dict] = []
    for key, label in FIELD_KEY_LABELS.items():
        entry = (fields or {}).get(key) or {}
        bbox = entry.get("bbox_norm")
        if not bbox or len(bbox) != 4:
            continue
        out.append(
            {
                "key": key,
                "label": label,
                "bbox_norm": [float(v) for v in bbox],
                "value": entry.get("value") or entry.get("raw") or "",
                "conf": entry.get("conf"),
            }
        )
    return out


templates.env.globals["is_admin"] = is_admin
templates.env.globals["is_master_admin"] = is_master_admin
templates.env.globals["can_add_document_links"] = can_add_document_links


async def _auth_create_user(
    request: Request,
    access_token: str | None,
    session: AsyncSession,
) -> Response | object:
    auth = await resolve_authenticated_user(request, access_token, session)
    if isinstance(auth, Response):
        return auth
    if not can_create_document(auth):
        raise HTTPException(status_code=403, detail="Недостаточно прав для создания документа.")
    return auth


@router.get("/ocr", response_class=HTMLResponse)
async def ocr_upload_page(
    request: Request,
    access_token: str | None = Cookie(None),
    session: AsyncSession = Depends(get_session),
):
    auth = await _auth_create_user(request, access_token, session)
    if isinstance(auth, Response):
        return auth

    return templates.TemplateResponse(
        "ocr_upload.html",
        {
            "request": request,
            "user": auth,
            "ocr_available": await ocr_service_available(),
            "allowed_extensions": sorted(OCR_ALLOWED_EXTENSIONS),
            "page_title": "Распознать из файла",
            "service_version": SERVICE_VERSION,
            "unread_count": 0,
            "dataset_url": url_path("/ocr/dataset"),
        },
    )


@router.get("/ocr/dataset", response_class=HTMLResponse)
async def ocr_dataset_page(
    request: Request,
    access_token: str | None = Cookie(None),
    session: AsyncSession = Depends(get_session),
):
    auth = await _auth_create_user(request, access_token, session)
    if isinstance(auth, Response):
        return auth
    stats = await dataset_stats(session)
    return templates.TemplateResponse(
        "ocr_dataset.html",
        {
            "request": request,
            "user": auth,
            "stats": stats,
            "page_title": "OCR датасет (этап 3)",
            "service_version": SERVICE_VERSION,
            "unread_count": 0,
        },
    )


@router.get("/api/ocr/dataset/stats")
async def api_ocr_dataset_stats(
    request: Request,
    access_token: str | None = Cookie(None),
    session: AsyncSession = Depends(get_session),
):
    auth = await _auth_create_user(request, access_token, session)
    if isinstance(auth, Response):
        return auth
    return await dataset_stats(session)


@router.post("/api/ocr/dataset/export")
async def api_ocr_dataset_export(
    request: Request,
    access_token: str | None = Cookie(None),
    session: AsyncSession = Depends(get_session),
):
    auth = await _auth_create_user(request, access_token, session)
    if isinstance(auth, Response):
        return auth
    body = {}
    try:
        body = await request.json()
    except Exception:
        body = {}
    mark = body.get("mark_exported", True)
    job_ids = body.get("job_ids")
    zip_bytes, summary = await build_dataset_zip(
        session,
        mark_exported=bool(mark),
        job_ids=job_ids if isinstance(job_ids, list) else None,
    )
    headers = {
        "Content-Disposition": f'attachment; filename="{summary["filename"]}"',
        "X-Dataset-Samples": str(summary["sample_count"]),
    }
    return StreamingResponse(io.BytesIO(zip_bytes), media_type="application/zip", headers=headers)


@router.post("/api/ocr/batches")
async def api_create_ocr_batch(
    request: Request,
    files: list[UploadFile] = File(...),
    access_token: str | None = Cookie(None),
    session: AsyncSession = Depends(get_session),
):
    auth = await _auth_create_user(request, access_token, session)
    if isinstance(auth, Response):
        return auth

    try:
        batch = await create_batch_with_files(session, auth, files)
    except HTTPException:
        raise
    except Exception as exc:
        # Most common deploy miss: migration not applied → missing ocr_* tables.
        message = str(exc)
        lowered = message.lower()
        if "ocr_batches" in lowered or "ocr_jobs" in lowered or "undefinedtable" in lowered.replace(" ", ""):
            raise HTTPException(
                status_code=503,
                detail=(
                    "Таблицы OCR не найдены. Выполните: "
                    "docker compose exec api alembic upgrade head "
                    "и перезапустите api (entrypoint также создаст ocr_* при старте). "
                    f"Детали: {message[:300]}"
                ),
            ) from exc
        raise HTTPException(
            status_code=500,
            detail=f"Не удалось создать пакет OCR: {message[:400]}",
        ) from exc

    return JSONResponse(
        {
            "ok": True,
            "batch_id": batch.id,
            "redirect": url_path(f"/ocr/batches/{batch.id}"),
        }
    )


@router.get("/api/ocr/batches/{batch_id}")
async def api_get_ocr_batch(
    batch_id: int,
    request: Request,
    access_token: str | None = Cookie(None),
    session: AsyncSession = Depends(get_session),
):
    auth = await _auth_create_user(request, access_token, session)
    if isinstance(auth, Response):
        return auth

    batch = await get_batch(session, batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Пакет OCR не найден.")
    return {
        "id": batch.id,
        "status": batch.status.value,
        "jobs": [
            {
                "id": j.id,
                "original_filename": j.original_filename,
                "status": j.status.value,
                "status_label": OCR_JOB_STATUS_LABELS.get(j.status, j.status.value),
                "error_message": j.error_message,
                "document_id": j.document_id,
                "review_url": url_path(f"/ocr/jobs/{j.id}/review"),
            }
            for j in batch.jobs
        ],
    }


@router.get("/ocr/batches/{batch_id}", response_class=HTMLResponse)
async def ocr_batch_page(
    batch_id: int,
    request: Request,
    access_token: str | None = Cookie(None),
    session: AsyncSession = Depends(get_session),
):
    auth = await _auth_create_user(request, access_token, session)
    if isinstance(auth, Response):
        return auth

    batch = await get_batch(session, batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Пакет OCR не найден.")

    return templates.TemplateResponse(
        "ocr_batch.html",
        {
            "request": request,
            "user": auth,
            "batch": batch,
            "page_title": f"OCR пакет #{batch.id}",
            "service_version": SERVICE_VERSION,
            "unread_count": 0,
        },
    )


@router.get("/ocr/jobs/{job_id}/review", response_class=HTMLResponse)
async def ocr_review_page(
    job_id: int,
    request: Request,
    access_token: str | None = Cookie(None),
    session: AsyncSession = Depends(get_session),
    error: str | None = None,
):
    auth = await _auth_create_user(request, access_token, session)
    if isinstance(auth, Response):
        return auth

    job = await get_job(session, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Задача OCR не найдена.")
    if job.status == OcrJobStatus.discarded:
        raise HTTPException(status_code=400, detail="Задача отклонена.")
    if job.status == OcrJobStatus.committed and job.document_id:
        return RedirectResponse(url=url_path(f"/documents/{job.document_id}"), status_code=303)

    extraction = latest_extraction(job)
    prefill = prefill_from_extraction(extraction)
    projects_result = await session.execute(select(Project).order_by(Project.name))
    projects = projects_result.scalars().all()
    known_names = await fetch_known_person_names(session)

    fields = (extraction.fields if extraction else {}) or {}
    geometry = (extraction.geometry if extraction else {}) or {}
    confidences = {key: field_confidence(fields, key) for key in fields}
    low_conf_fields = set(geometry.get("low_conf_fields") or [])
    for key, conf in confidences.items():
        if conf is not None and conf < OCR_LOW_CONF_THRESHOLD:
            low_conf_fields.add(key)

    # Fresh suggestions at review time (org near-misses like РЕТР→ФЕТР)
    stored_suggestions = dict((extraction.person_suggestions if extraction else {}) or {})
    live_suggestions = await _build_field_suggestions(session, fields)
    if prefill.get("org_code"):
        known_orgs = await fetch_known_org_codes(session)
        live_suggestions["org_code"] = suggest_org_codes(prefill["org_code"], known_orgs, limit=5)
    person_suggestions = {**stored_suggestions, **live_suggestions}

    return templates.TemplateResponse(
        "ocr_review.html",
        {
            "request": request,
            "user": auth,
            "job": job,
            "extraction": extraction,
            "prefill": prefill,
            "date_hints": date_hints_from_extraction(extraction),
            "projects": projects,
            "known_person_names": known_names,
            "person_suggestions": person_suggestions,
            "field_confidences": confidences,
            "low_conf_fields": low_conf_fields,
            "low_conf_threshold": OCR_LOW_CONF_THRESHOLD,
            "geometry": geometry,
            "stamp_crop_url": (
                url_path(f"/api/ocr/jobs/{job.id}/stamp-crop")
                if extraction and extraction.stamp_crop_path
                else None
            ),
            "page_preview_url": (
                url_path(f"/api/ocr/jobs/{job.id}/page-preview")
                if extraction and extraction.page_preview_path
                else None
            ),
            "field_rois": _field_rois_for_review(fields),
            "annotate_url": url_path(f"/ocr/jobs/{job.id}/annotate"),
            "ocr_available": await ocr_service_available(),
            "error": error,
            "default_developed_by": prefill.get("developed_by") or auth.full_name or "",
            "page_count": geometry.get("page_count") or job.page_count,
            "has_specification": bool(geometry.get("has_specification")),
            "spec_page_indices": geometry.get("spec_page_indices") or [],
            "spec_designations": geometry.get("spec_designations") or [],
            "search_designations_url": url_path("/api/documents/search-designations"),
            "page_title": f"Сверка OCR — {job.original_filename}",
            "service_version": SERVICE_VERSION,
            "unread_count": 0,
        },
    )


@router.get("/ocr/jobs/{job_id}/annotate", response_class=HTMLResponse)
async def ocr_annotate_page(
    job_id: int,
    request: Request,
    access_token: str | None = Cookie(None),
    session: AsyncSession = Depends(get_session),
):
    auth = await _auth_create_user(request, access_token, session)
    if isinstance(auth, Response):
        return auth

    job = await get_job(session, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Задача OCR не найдена.")
    if job.status == OcrJobStatus.discarded:
        raise HTTPException(status_code=400, detail="Задача отклонена.")
    if job.status == OcrJobStatus.committed and job.document_id:
        return RedirectResponse(url=url_path(f"/documents/{job.document_id}"), status_code=303)

    extraction = latest_extraction(job)
    annotation = await latest_annotation(session, job_id)
    bootstrap = await annotation_bootstrap(session, job, extraction, annotation)

    return templates.TemplateResponse(
        "ocr_annotate.html",
        {
            "request": request,
            "user": auth,
            "job": job,
            "extraction": extraction,
            "bootstrap": bootstrap,
            "field_key_labels": FIELD_KEY_LABELS,
            "stamp_crop_url": (
                url_path(f"/api/ocr/jobs/{job.id}/stamp-crop")
                if bootstrap.get("has_stamp_crop")
                else None
            ),
            "page_preview_url": (
                url_path(f"/api/ocr/jobs/{job.id}/page-preview")
                if bootstrap.get("has_page_preview")
                else None
            ),
            "review_url": url_path(f"/ocr/jobs/{job.id}/review"),
            "page_title": f"Разметка штампа — {job.original_filename}",
            "service_version": SERVICE_VERSION,
            "unread_count": 0,
        },
    )


@router.get("/api/ocr/jobs/{job_id}/annotations")
async def api_get_annotation(
    job_id: int,
    request: Request,
    access_token: str | None = Cookie(None),
    session: AsyncSession = Depends(get_session),
):
    auth = await _auth_create_user(request, access_token, session)
    if isinstance(auth, Response):
        return auth
    job = await get_job(session, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Задача OCR не найдена.")
    extraction = latest_extraction(job)
    annotation = await latest_annotation(session, job_id)
    return await annotation_bootstrap(session, job, extraction, annotation)


@router.post("/api/ocr/jobs/{job_id}/annotations")
async def api_save_annotation(
    job_id: int,
    request: Request,
    access_token: str | None = Cookie(None),
    session: AsyncSession = Depends(get_session),
):
    auth = await _auth_create_user(request, access_token, session)
    if isinstance(auth, Response):
        return auth
    job = await get_job(session, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Задача OCR не найдена.")
    body = await request.json()
    annotation = await save_annotation(session, job, auth, body)
    return {"ok": True, "annotation_id": annotation.id, "labels": annotation.labels}


@router.post("/api/ocr/jobs/{job_id}/reocr")
async def api_reocr_annotated(
    job_id: int,
    request: Request,
    access_token: str | None = Cookie(None),
    session: AsyncSession = Depends(get_session),
):
    auth = await _auth_create_user(request, access_token, session)
    if isinstance(auth, Response):
        return auth
    job = await get_job(session, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Задача OCR не найдена.")
    body = await request.json()
    labels = body if body.get("cells") else None
    await reocr_from_annotation(session, job, auth, labels_raw=labels)
    return JSONResponse(
        {
            "ok": True,
            "redirect": url_path(f"/ocr/jobs/{job_id}/review"),
        }
    )


@router.post("/api/ocr/jobs/{job_id}/commit")
async def api_commit_ocr_job(
    job_id: int,
    request: Request,
    access_token: str | None = Cookie(None),
    session: AsyncSession = Depends(get_session),
):
    auth = await _auth_create_user(request, access_token, session)
    if isinstance(auth, Response):
        return auth

    job = await get_job(session, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Задача OCR не найдена.")

    form_data = await request.form()
    form = dict(form_data)
    form["additional_product_ids"] = form_data.getlist("additional_product_ids")
    form["link_target_ids"] = form_data.getlist("link_target_ids")
    try:
        doc = await commit_ocr_job(session, job, auth, form)
    except HTTPException as exc:
        if not wants_json_response(request):
            return RedirectResponse(
                url=url_path(f"/ocr/jobs/{job_id}/review?error={quote(str(exc.detail))}"),
                status_code=303,
            )
        raise

    redirect = url_path(f"/documents/{doc.id}")
    if wants_json_response(request) or form.get("_ajax") == "1":
        return JSONResponse({"ok": True, "document_id": doc.id, "redirect": redirect})
    return RedirectResponse(url=redirect, status_code=303)


@router.post("/api/ocr/jobs/{job_id}/retry")
async def api_retry_ocr_job(
    job_id: int,
    request: Request,
    access_token: str | None = Cookie(None),
    session: AsyncSession = Depends(get_session),
):
    auth = await _auth_create_user(request, access_token, session)
    if isinstance(auth, Response):
        return auth

    job = await get_job(session, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Задача OCR не найдена.")
    job = await retry_job(session, job)
    if wants_json_response(request):
        return JSONResponse(
            {
                "ok": True,
                "status": job.status.value,
                "error_message": job.error_message,
                "redirect": url_path(f"/ocr/jobs/{job.id}/review"),
            }
        )
    return RedirectResponse(url=url_path(f"/ocr/jobs/{job.id}/review"), status_code=303)


@router.post("/api/ocr/jobs/{job_id}/discard")
async def api_discard_ocr_job(
    job_id: int,
    request: Request,
    access_token: str | None = Cookie(None),
    session: AsyncSession = Depends(get_session),
):
    auth = await _auth_create_user(request, access_token, session)
    if isinstance(auth, Response):
        return auth

    job = await get_job(session, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Задача OCR не найдена.")
    batch_id = job.batch_id
    await discard_job(session, job, user=auth)
    if wants_json_response(request):
        return JSONResponse({"ok": True, "redirect": url_path(f"/ocr/batches/{batch_id}")})
    return RedirectResponse(url=url_path(f"/ocr/batches/{batch_id}"), status_code=303)


@router.post("/api/ocr/jobs/{job_id}/save-training")
async def api_save_training_example(
    job_id: int,
    request: Request,
    access_token: str | None = Cookie(None),
    session: AsyncSession = Depends(get_session),
):
    """Save corrected review fields as a training example without creating a document."""
    auth = await _auth_create_user(request, access_token, session)
    if isinstance(auth, Response):
        return auth

    job = await get_job(session, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Задача OCR не найдена.")

    form = dict(await request.form())
    try:
        await save_training_example(session, job, auth, form)
    except HTTPException as exc:
        if wants_json_response(request):
            return JSONResponse({"ok": False, "detail": exc.detail}, status_code=exc.status_code)
        return await ocr_review_page(
            job_id, request, access_token, session, error=str(exc.detail)
        )

    batch_id = job.batch_id
    if wants_json_response(request):
        return JSONResponse(
            {
                "ok": True,
                "status": "labeled",
                "redirect": url_path(f"/ocr/batches/{batch_id}"),
            }
        )
    return RedirectResponse(url=url_path(f"/ocr/batches/{batch_id}"), status_code=303)


@router.get("/api/ocr/jobs/{job_id}/stamp-crop")
async def api_ocr_stamp_crop(
    job_id: int,
    request: Request,
    access_token: str | None = Cookie(None),
    session: AsyncSession = Depends(get_session),
):
    auth = await _auth_create_user(request, access_token, session)
    if isinstance(auth, Response):
        return auth

    job = await get_job(session, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Задача OCR не найдена.")
    extraction = latest_extraction(job)
    path = extraction.stamp_crop_path if extraction else None
    if not path or not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="Превью штампа не найдено.")
    # Path must stay under UPLOAD_DIR
    abs_upload = os.path.abspath(UPLOAD_DIR)
    abs_path = os.path.abspath(path)
    if not (abs_path == abs_upload or abs_path.startswith(abs_upload + os.sep)):
        raise HTTPException(status_code=404, detail="Превью штампа не найдено.")
    return FileResponse(abs_path, media_type="image/png", filename=os.path.basename(abs_path))


@router.get("/api/ocr/jobs/{job_id}/page-preview")
async def api_ocr_page_preview(
    job_id: int,
    request: Request,
    access_token: str | None = Cookie(None),
    session: AsyncSession = Depends(get_session),
):
    auth = await _auth_create_user(request, access_token, session)
    if isinstance(auth, Response):
        return auth

    job = await get_job(session, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Задача OCR не найдена.")
    extraction = latest_extraction(job)
    path = extraction.page_preview_path if extraction else None
    if not path or not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="Превью листа не найдено.")
    abs_upload = os.path.abspath(UPLOAD_DIR)
    abs_path = os.path.abspath(path)
    if not (abs_path == abs_upload or abs_path.startswith(abs_upload + os.sep)):
        raise HTTPException(status_code=404, detail="Превью листа не найдено.")
    return FileResponse(abs_path, media_type="image/png", filename=os.path.basename(abs_path))


@router.get("/api/ocr/health")
async def api_ocr_health(
    request: Request,
    access_token: str | None = Cookie(None),
    session: AsyncSession = Depends(get_session),
):
    auth = await resolve_authenticated_user(request, access_token, session)
    if isinstance(auth, Response):
        return auth
    return {"available": await ocr_service_available()}
