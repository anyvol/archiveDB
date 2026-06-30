# archiveDB

**archiveDB** is a web-based document archive for engineering organizations. It stores design documentation (KD — конструкторская документация) and technological documentation (TD — технологическая документация) with Russian-standard designations (PRNI/PRN numbering), file uploads, review workflow, and role-based access control.

The system is built for teams that need a single place to register documents, attach files, track verification status, and receive notifications when records change. It provides both a browser UI and a REST API, runs in Docker with PostgreSQL, and supports browser push notifications over HTTPS.

## Features

- Register KD and TD documents with automatic PRNI/PRN numbering
- Upload files to local disk (Docker bind mount)
- Status workflow: **Pending review** → **Verified** / **Requires correction**
- Roles: **user**, **reviewer**, **admin**
- Filter and sort all table columns
- REST API (`/docs`) and web UI
- Browser push notifications (HTTPS required)
- Changelog page linked from the header

## Roles and permissions

| Action | user | reviewer | admin |
|--------|------|----------|-------|
| View and download all documents | yes | yes | yes |
| Create documents | yes | no | yes |
| First file upload | yes (own) | no | yes (any) |
| Replace file | only when **Requires correction** | no | yes |
| Set **Verified** / **Requires correction** | no | yes | yes |
| Edit metadata | no | no | yes |
| Delete | no | no | yes |

Roles **admin** and **reviewer** are assigned manually (not via registration).

## Quick start (Docker)

```bash
cp .env.example .env
# Edit SECRET_KEY, passwords, and optionally SSL_CERT_CN in .env

docker compose up --build
```

Application: **http://localhost/archive/** (push works) or **https://localhost:8443/archive/**

HTTP on `localhost` is enough for browser push (browsers treat localhost as secure). Use **https://SERVER-PDM:8443/archive/** for LAN access.

For LAN access, set in `.env`:

```env
SSL_CERT_CN=SERVER-PDM
```

Then remove old certs and restart proxy:

```bash
rm -f nginx/certs/*.pem
docker compose up -d proxy
```

Open: `https://SERVER-PDM:8443/archive/`

Files are stored on the host at `./uploaded_files` (configure via `UPLOAD_HOST_PATH` in `.env`).

## Browser push notifications

1. Generate VAPID keys inside the API container:

   ```bash
   docker compose exec api python -m py_vapid --applicationServerKey
   ```

2. Add to `.env`:

   ```env
   VAPID_PUBLIC_KEY=Application_Server_Key_from_output
   VAPID_PRIVATE_KEY=/app/private_key.pem
   VAPID_SUBJECT=mailto:admin@example.com
   ```

3. Restart API: `docker compose up -d api`

4. Open the site over **HTTPS**, go to **Profile** → **Connect push**

Push does not work over plain HTTP (except `localhost`). HTTPS is required by browser security policy.

## Assign roles manually

```bash
docker compose exec api python scripts/promote_user.py ivanov admin
docker compose exec api python scripts/promote_user.py petrov reviewer
```

See [docs/README.md](docs/README.md) for more details.

## Local run without Docker

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Set DATABASE_URL to local PostgreSQL

uvicorn app.main:app --reload
```

## Migrations

```bash
docker compose exec api alembic upgrade head
```

## Environment variables

See [.env.example](.env.example):

- `DATABASE_URL` — async PostgreSQL URL
- `SECRET_KEY` — required for JWT
- `ROOT_PATH` — URL prefix behind reverse proxy (default `/archive`)
- `UPLOAD_DIR`, `UPLOAD_HOST_PATH` — file storage
- `VAPID_*` — browser push (optional)
- `SSL_CERT_CN` — hostname for self-signed certificate

## File naming on upload

If the uploaded file name (without extension) does not match the document designation, the file is stored as:

```text
{designation}({original_basename}){extension}
```

Example: designation `ORG.123456.001`, file `report.pdf` → stored as `ORG.123456.001(report).pdf`.

## Tests

```bash
pip install -r requirements.txt
pytest
```

## Document designations

- **KD:** `ORG.123456.001` + optional kind code (e.g. `СБ`)
- **TD:** `ORG.1234567.001` (7-digit class code, PRN)

Organization code: 4 Russian letters or 8 digits (OKPO).
