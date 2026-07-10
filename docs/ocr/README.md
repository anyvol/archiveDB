# OCR pipeline notes

## Architecture

```text
Browser  →  proxy (:80/:8443)  →  api (:8000)  →  ocr (:9003, internal only)
                                      ↓
                                   Postgres
                                      ↓
                         uploaded_files/  (shared volume)
```

- Migrations run on **api container start** (`scripts/docker-entrypoint.sh`: `alembic upgrade head` + `ensure_schema.py`), not during image build.
- Browser never talks to OCR directly. Main `api` uses `OCR_SERVICE_URL=http://ocr:9003`.
- Staging: `uploaded_files/_ocr_inbox/{batch_id}/` (+ `crops/`).

## Phase 1B (current)

Pipeline inside `ocr` service:

1. Render PDF/image (PyMuPDF / Pillow), DPI default 250  
2. Light deskew (OpenCV)  
3. Stamp ROI (bottom-right, ГОСТ 2.104 approx)  
4. Cell template OCR (Tesseract `rus+eng` by default; optional `OCR_ENGINE=paddle` if PaddleOCR installed)  
5. Prefill designation / name / FIO / dates / format  
6. API adds fuzzy FIO suggestions (`rapidfuzz`) — chips on review, no silent replace  
7. Low-confidence fields highlighted; weak extract → `needs_annotation`

## Deploy

```bash
docker compose up -d --build
docker compose exec api alembic upgrade head   # also runs automatically on api start
docker compose exec api python -c "import urllib.request; print(urllib.request.urlopen('http://ocr:9003/health').read().decode())"
docker compose exec db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c '\dt ocr_*'
```

Recommended `.env`:

```env
OCR_SERVICE_TIMEOUT_SEC=120
OCR_LOW_CONF_THRESHOLD=0.5
```

First OCR call may be slower (model/warmup). Rebuild **ocr** image after pulling 1B (tesseract + OpenCV deps).

## Next

- Phase 2: annotation UI + re-OCR by manual bboxes  
- Phase 3: dataset ZIP export / DVC / MLflow / trained detector  
