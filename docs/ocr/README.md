# OCR pipeline notes (phase 1A)

## Architecture

```text
Browser  →  proxy (:80/:8443)  →  api (:8000)  →  ocr (:9003, internal only)
                                      ↓
                                   Postgres
                                      ↓
                         uploaded_files/  (shared volume)
```

- `ocr/` — separate FastAPI sidecar on **internal** port 9003 (`expose`, not `ports`).
- Browser never talks to OCR directly. Main `api` uses `OCR_SERVICE_URL=http://ocr:9003`.
- If the sidecar is down, the archive still works; OCR jobs are marked `failed` and can be filled manually on the review screen.
- Staging files: `uploaded_files/_ocr_inbox/{batch_id}/` (API path `/app/uploaded_files/...`, OCR path `/uploads/...`).

## Deploy checklist

```bash
docker compose up -d --build
docker compose exec api alembic upgrade head   # required: creates ocr_* tables

# Health (from inside the Docker network — NOT localhost:9003 on the host)
docker compose exec api python -c "import urllib.request; print(urllib.request.urlopen('http://ocr:9003/health').read().decode())"
# or:
docker compose exec ocr python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:9003/health').read().decode())"
```

`curl http://localhost:9003/health` on the host returns nothing by design — port 9003 is not published.

## Phase 1A scope

- Batch upload UI (`/ocr`) linked from Documents → Ещё → «Распознать из файла»
- Jobs + extractions tables
- Stub extract: sheet format from PDF/image dimensions; stamp fields empty
- Review + commit creates DD/TD + attaches the staged file

## Next

- Phase 1B: real stamp OCR (ROI + cell templates + PaddleOCR)
- Phase 2: annotation UI
- Phase 3: dataset export / DVC / MLflow
