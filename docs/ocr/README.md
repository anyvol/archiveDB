# OCR pipeline notes

## Architecture

```text
Browser  →  proxy → api → ocr (:9003, internal)
                 ↘ Postgres
                 ↘ uploaded_files/ (shared volume)
```

Migrations run on **api start** (`alembic upgrade head` + `ensure_schema.py`), not on image build.

## Phase 1B — auto extract

Render → deskew → stamp ROI → cell template OCR (Tesseract rus+eng by default).

Paper format is detected from page/image dimensions and from the stamp «формат» cell. Values are normalized to codes like `A4`, `A3x3` (Cyrillic «А» → Latin «A»). If OCR format text is invalid, dimensions win so the review dropdown can be prefilled.

If a **format-bound ROI template** exists for that code, auto extract re-runs cell OCR with those boxes after the first stamp crop.

## Phase 2 — annotation

When auto cell boxes miss the real stamp layout:

1. On review click **«Разметить ячейки»** → `/ocr/jobs/{id}/annotate`
2. Drag/resize boxes on the stamp crop, assign field types (including three **signature** ROIs)
3. Optional: enter ground-truth text for a cell (skips OCR for that cell)
4. **Сохранить разметку** and/or **Перераспознать по разметке**
5. Back to review with updated fields (`source=annotated`)

Stored in `ocr_annotations.labels` (JSON cells + bbox_norm). On save, the same cells are upserted into `ocr_format_templates` keyed by `document_format`.

Sidecar endpoints: `POST /v1/extract`, `POST /v1/extract-cells`.

### Signatures

ROI keys: `developer_signature`, `reviewer_signature`, `approver_signature`.  
Rule: if the crop has any meaningful ink (dark pixels), the field value is `true`.  
On commit, booleans are stored on `documents.has_*_signature`.

### Review prefill

- Dates → `YYYY-MM-DD` for `<input type="date">`
- Doc kind from designation suffix (СБ, СП, …)
- Org code / FIO suggestion chips (never auto-applied)
- Project/product: select existing only (create them under Projects)

## Deploy

```bash
git pull
docker compose up -d --build
docker compose exec api alembic upgrade head   # → p6q7r8s9t0u1
docker compose exec db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c '\dt ocr_*'
```

## Next (phase 3)

Dataset ZIP export from annotations / corrected extractions, DVC/MLflow, trained detector.
