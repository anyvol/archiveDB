# OCR phase 3 — operator guide

## What phase 3 adds

1. **Higher render DPI (400)** — clearer stamp text for OCR and annotation previews.
2. **Dataset ZIP export** — from the UI (`/ocr/dataset`) or `POST /api/ocr/dataset/export`.
3. **Training toolkit** — `ocr/training/` converts the ZIP to YOLO format and trains a stamp detector (Ultralytics), with optional MLflow + DVC stubs.
4. **Optional detector at runtime** — if `OCR_STAMP_DETECTOR_PATH` points to a `.pt` model inside the OCR container, the sidecar uses it to find the title block before falling back to format templates / defaults.

The API container still does **not** run heavy training. Training is offline; only the resulting weights are mounted into `ocr`.

---

## Day-to-day OCR workflow (after phase 3)

```text
1. Documents → Ещё → «Распознать из файла»
2. Upload PDF/images → batch page
3. Open «Сверка» for each job
4. If stamp crop is wrong (typical A4 vs A3):
     «Разметить штамп и ячейки»
       → tab «Область штампа на листе»  (page ROI)
       → tab «Ячейки штампа»            (field boxes)
       → «Перераспознать по разметке»
     ROI is saved for that paper format (A4/A3/…)
5. Fix fields (org chips, dates, kind, signatures)
6. Either:
     a) Select project/product → «Принять и создать документ»
     b) «Сохранить как учебный пример» (no archive card, keeps GT for training)
     c) «Отклонить» (annotations / format template still kept)
7. Periodically: /ocr/dataset → «Скачать датасет ZIP» → train detector offline
8. Deploy best.pt into OCR sidecar → better automatic stamp location
```

### Recognition order for stamp location

1. Explicit ROI from format template / human annotation (if present)
2. Else trained detector (`OCR_STAMP_DETECTOR_PATH`), if enabled and confident
3. Else format-specific default box (A4 ≠ A3)
4. Else built-in default

Cell OCR then uses cell boxes from the format template (if any), else the built-in GOST approx template. Engine: Tesseract `rus+eng` (or Paddle if configured).

---

## Export dataset

### UI

1. Open `/ocr` → link **«Датасет (этап 3)»** (also on batch page).
2. Check counts (exportable jobs, format templates).
3. Click **«Скачать датасет ZIP»**.

### API

```bash
# from a logged-in browser session cookie, or via curl with auth cookie
curl -X POST -H 'Content-Type: application/json' \
  -b 'access_token=...' \
  -o dataset.zip \
  https://YOUR_HOST/api/ocr/dataset/export \
  -d '{"mark_exported": true}'
```

### ZIP contents

```text
archivedb-ocr-dataset-YYYYMMDD-HHMMSS/
  manifest.json
  format_templates.json
  README.txt
  samples/job_<id>/
    labels.json      # stamp_roi_norm, cells, ground_truth_fields
    stamp.png        # title-block crop
    page.png         # page preview (needed to train stamp detector)
```

Samples included when a job has annotations and/or extractions with
`source` in `training|corrected|annotated|annotated_stamp`.

---

## Train stamp detector (offline)

```bash
python ocr/training/prepare_yolo_dataset.py \
  --zip ./dataset.zip \
  --out ./data/stamp_yolo

pip install ultralytics mlflow
python ocr/training/train_stamp_detector.py \
  --data ./data/stamp_yolo/data.yaml \
  --epochs 80 \
  --imgsz 1280 \
  --project ./data/stamp_runs \
  --mlflow-uri ./mlruns
```

Copy `data/stamp_runs/detect/weights/best.pt` to `./models/stamp_detector.pt`.

### Wire into Docker

`docker-compose.yaml` / `.env`:

```yaml
ocr:
  environment:
    OCR_RENDER_DPI: "400"
    OCR_STAMP_DETECTOR_PATH: /models/stamp_detector.pt
  volumes:
    - ${UPLOAD_HOST_PATH:-./uploaded_files}:/uploads
    - ./models:/models:ro
```

```bash
docker compose up -d --build ocr
docker compose exec api python -c "import urllib.request; print(urllib.request.urlopen('http://ocr:9003/health').read().decode())"
# expect stamp_detector: on
```

Until a model is present, the pipeline keeps using format templates (already useful after a few A4/A3 annotations).

---

## DVC / MLflow

- `ocr/training/dvc.yaml` + `params.yaml` — optional reproducible stages (`prepare` → `train`).
- `train_stamp_detector.py --mlflow-uri ./mlruns` — logs params/metrics/artifacts locally.
- Remote MLflow: set `--mlflow-uri http://mlflow:5000` on your training host.

---

## Deploy checklist (0.25.0)

```bash
git pull
docker compose up -d --build
docker compose exec api alembic upgrade head
# optional: OCR_RENDER_DPI=400 already default in compose
```

No new Alembic revision is required for phase 3 export (uses existing OCR tables).

---

## What improves recognition today vs after training

| Mechanism | When it helps |
|-----------|----------------|
| Format-bound stamp + cell ROI templates | Immediately after you annotate one sheet of that format |
| Org/FIO suggestion chips | Immediately from DB |
| Higher DPI (400) | Immediately on next OCR run |
| Trained stamp detector | After export → train → mount `best.pt` |
| Cell-level ML detector | Future; export already includes cell boxes for that |
