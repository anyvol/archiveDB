# OCR pipeline notes (phase 1A)

## Architecture

- `ocr/` — separate FastAPI sidecar (`ocr` service in docker-compose), port 9003.
- Main `api` talks to it only via HTTP (`OCR_SERVICE_URL`). If the sidecar is down, document archive still works; OCR jobs are marked `failed` and can be filled manually on the review screen.
- Staging files live under `uploaded_files/_ocr_inbox/{batch_id}/`.

## Phase 1A scope

- Batch upload UI (`/ocr`) linked from Documents → Ещё → «Распознать из файла»
- Jobs + extractions tables
- Stub extract: sheet format from PDF/image dimensions; stamp fields empty
- Review + commit creates DD/TD + attaches the staged file

## Next

- Phase 1B: real stamp OCR (ROI + cell templates + PaddleOCR)
- Phase 2: annotation UI
- Phase 3: dataset export / DVC / MLflow
