# OCR training toolkit (phase 3)

Offline tools that consume the dataset ZIP exported from the archive UI
(`/ocr/dataset` → «Скачать датасет ZIP»).

Heavy training stays **out of the API container**. Run these scripts on a
workstation/GPU host, then mount the resulting model into the `ocr` service.

## Quick start

```bash
# 1) Export ZIP from the web UI (or API POST /api/ocr/dataset/export)

# 2) Convert to YOLO layout for stamp detection
python ocr/training/prepare_yolo_dataset.py \
  --zip ~/Downloads/archivedb-ocr-dataset-*.zip \
  --out ./data/stamp_yolo

# 3) Train (requires ultralytics)
pip install ultralytics mlflow
python ocr/training/train_stamp_detector.py \
  --data ./data/stamp_yolo/data.yaml \
  --epochs 80 \
  --imgsz 1280 \
  --mlflow-uri ./mlruns

# 4) Deploy model into OCR sidecar
# copy best.pt → ./models/stamp_detector.pt
# in .env / compose:
#   OCR_STAMP_DETECTOR_PATH=/models/stamp_detector.pt
# mount: ./models:/models:ro
docker compose up -d --build ocr
```

## DVC (optional)

```bash
cd ocr/training
dvc init --subdir   # once
dvc repro           # runs prepare → train stages when configured
```

See `dvc.yaml` and `docs/ocr/PHASE3.md`.
