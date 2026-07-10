# OCR pipeline notes

## Architecture

```text
Browser  →  proxy → api → ocr (:9003, internal)
                 ↘ Postgres
                 ↘ uploaded_files/ (shared volume)
                 ↘ models/ (optional stamp detector .pt)
```

Migrations run on **api start** (`alembic upgrade head` + `ensure_schema.py`), not on image build.

## Phase 1B — auto extract

Render (default **400 DPI**) → deskew → stamp ROI → cell template OCR (Tesseract rus+eng by default).

Paper format is detected from page/image dimensions and from the stamp «формат» cell. Values are normalized to codes like `A4`, `A3x3` (Cyrillic «А» → Latin «A»). If OCR format text is invalid, dimensions win so the review dropdown can be prefilled.

If a **format-bound ROI template** exists for that code, auto extract uses its stamp ROI and cell boxes.

## Phase 2 — annotation

When auto cell boxes miss the real stamp layout:

1. On review click **«Разметить штамп и ячейки»** → `/ocr/jobs/{id}/annotate`
2. Tab **«Область штампа на листе»** — drag the box on the page preview (A4 ≠ A3)
3. Tab **«Ячейки штампа»** — drag/resize boxes on the stamp crop, assign field types (including three **signature** ROIs)
4. Optional: enter ground-truth text for a cell (skips OCR for that cell)
5. **Сохранить разметку** and/or **Перераспознать по разметке**
6. Back to review with updated fields (`source=annotated`)

Stored in `ocr_annotations.labels` (JSON cells + bbox_norm + stamp_roi_norm). On save, the same labels are upserted into `ocr_format_templates` keyed by `document_format`.

Sidecar endpoints: `POST /v1/extract`, `POST /v1/extract-cells`.

### Signatures

ROI keys: `developer_signature`, `reviewer_signature`, `approver_signature`.  
Rule: if the crop has any meaningful ink (dark pixels), the field value is `true`.  
On commit, booleans are stored on `documents.has_*_signature`.

### Review prefill

- Dates → `YYYY-MM-DD` for `<input type="date">` (including `dd.mm.yy`)
- Doc kind from designation suffix (СБ, СП, …), including Latin OCR aliases (`CB` → `СБ`)
- Org code / FIO suggestion chips (never auto-applied); near-misses like РЕТР→ФЕТР
- Project/product: select existing only (create them under Projects)

### Review ROI previews

The review page shows per-cell crop thumbnails (what each ROI sent to OCR).

- **«Сохранить как учебный пример»** stores corrected fields (`ocr_extractions.source=training`, job status `labeled`) without creating an archive card.
- **Discard** keeps cell annotations and upserts the format-bound ROI template.

## Phase 3 — dataset + optional detector

See **[PHASE3.md](./PHASE3.md)** for the full operator guide.

Summary:

1. Collect annotations / training examples in the UI
2. `/ocr/dataset` → download ZIP
3. Offline: `ocr/training/prepare_yolo_dataset.py` → `train_stamp_detector.py`
4. Mount `best.pt` as `OCR_STAMP_DETECTOR_PATH=/models/stamp_detector.pt`

### Stamp location priority

1. Explicit ROI from format template / annotation  
2. Trained detector (if `OCR_STAMP_DETECTOR_PATH` set and confident)  
3. Format-specific default box  
4. Built-in default  

## Deploy

```bash
git pull
docker compose up -d --build
docker compose exec api alembic upgrade head   # → p6q7r8s9t0u1
docker compose exec db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c '\dt ocr_*'
# OCR health (from api container, not host):
docker compose exec api python -c "import urllib.request; print(urllib.request.urlopen('http://ocr:9003/health').read().decode())"
```
