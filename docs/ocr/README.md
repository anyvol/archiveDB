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

## Phase 2 — annotation (current)

When auto cell boxes miss the real stamp layout:

1. On review click **«Разметить ячейки»** → `/ocr/jobs/{id}/annotate`
2. Drag/resize boxes on the stamp crop, assign field types
3. Optional: enter ground-truth text for a cell (skips OCR for that cell)
4. **Сохранить разметку** and/or **Перераспознать по разметке**
5. Back to review with updated fields (`source=annotated`)

Stored in `ocr_annotations.labels` (JSON cells + bbox_norm). Sidecar endpoint: `POST /v1/extract-cells`.

## Deploy

```bash
git pull
docker compose up -d --build
docker compose exec api alembic upgrade head   # → o5p6q7r8s9t0
docker compose exec db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c '\dt ocr_*'
```

## Next (phase 3)

Dataset ZIP export from annotations / corrected extractions, DVC/MLflow, trained detector.
