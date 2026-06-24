# Deployment guide

## Architecture

```text
Users → Nginx (proxy :80) → /archive/ → FastAPI (api :8000, internal)
                          → /health  → health check
                          → /        → redirect to /archive/documents
         PostgreSQL (db, internal network only)
         Uploaded files (host bind mount → /app/uploaded_files)
```

Future microservices are added as new Docker services and new `location` blocks in [`deploy/nginx/conf.d/archive.conf`](deploy/nginx/conf.d/archive.conf).

## Requirements

- Docker Desktop (Windows) or Docker Engine (Linux)
- Docker Compose v2
- Git (optional, for `deploy` scripts with `git pull`)

On **Windows Server**, use **PowerShell** scripts (`*.ps1`). Bash scripts work in Git Bash or WSL.

## First-time setup

### 1. Clone and configure

```powershell
git clone <repo-url> archive-app
cd archive-app
copy .env.example .env
```

Edit `.env`:

| Variable | Notes |
|----------|-------|
| `POSTGRES_PASSWORD` | Strong password |
| `SECRET_KEY` | `openssl rand -hex 32` |
| `UPLOAD_HOST_PATH` | See path examples below |
| `APP_BASE_PATH` | `/archive` (default, do not change unless you change Nginx) |

### 2. File storage paths (Windows)

Use **forward slashes** in `.env` for Docker bind mounts:

```env
# Relative (recommended for beta — works on Windows and Linux)
UPLOAD_HOST_PATH=./data/uploads
BACKUP_DIR=./data/backups

# Absolute on Windows (Docker Desktop)
UPLOAD_HOST_PATH=C:/archive/data/uploads
BACKUP_DIR=C:/archive/data/backups
```

Create directories if using absolute paths:

```powershell
New-Item -ItemType Directory -Force -Path C:\archive\data\uploads
New-Item -ItemType Directory -Force -Path C:\archive\data\backups
```

### 3. Start production stack

```powershell
docker compose up -d --build
```

Open: **http://localhost/archive/documents**

Root `/` redirects to `/archive/documents`.

### 4. Create admin user

1. Register at `/archive/register`
2. Promote role:

```powershell
docker compose exec api python scripts/promote_user.py <login> admin
```

## Development (local)

Direct API access without Nginx prefix:

```powershell
docker compose -f docker-compose.yaml -f docker-compose.dev.yaml up --build
```

Open: **http://localhost:8000/documents** (`APP_BASE_PATH` is empty in dev override).

To test with Nginx locally:

```powershell
docker compose -f docker-compose.yaml -f docker-compose.dev.yaml --profile with-proxy up --build
```

## Updating without data loss

Data is stored in:

- Docker volume `pgdata` (PostgreSQL)
- Host directory `UPLOAD_HOST_PATH` (uploaded files)

**Never run** `docker compose down -v` on production — `-v` deletes the database volume.

### Update workflow

**Windows (PowerShell):**

```powershell
.\scripts\deploy.ps1
```

**Linux / Git Bash:**

```bash
./scripts/deploy.sh
```

The deploy script:

1. Backs up DB and files
2. `git pull` (if git repo)
3. Rebuilds `api` and `proxy`
4. Runs Alembic migrations
5. Health check on `/health`

Skip backup: `.\scripts\deploy.ps1 -SkipBackup`

### Manual update

```powershell
.\scripts\backup.ps1
git pull
docker compose build api proxy
docker compose up -d
docker compose exec api python run_migrations.py upgrade head
.\scripts\healthcheck.ps1
```

## Database migrations

1. Change models in `app/models.py`
2. Generate migration (dev machine):

```bash
python run_migrations.py revision --autogenerate -m "description"
```

3. Review file in `alembic/versions/`
4. Deploy — migrations run automatically via API entrypoint and `deploy` script

Production uses Alembic only (`AUTO_CREATE_TABLES=false`). Dev can use `AUTO_CREATE_TABLES=true` for quick local starts.

## Backups and restore

### Backup

```powershell
.\scripts\backup.ps1
```

Creates `db_YYYYMMDD_HHMMSS.sql` and `files_YYYYMMDD_HHMMSS.tar.gz` in `BACKUP_DIR`.

### Restore database

```powershell
Get-Content .\data\backups\db_YYYYMMDD_HHMMSS.sql | docker compose exec -T db psql -U archiveuser archivedb
```

### Restore files

```powershell
tar -xzf .\data\backups\files_YYYYMMDD_HHMMSS.tar.gz -C .
```

## Adding a new microservice

1. Add service to [`docker-compose.yaml`](docker-compose.yaml) (no host `ports`, only `expose`)
2. Add routing in [`deploy/nginx/conf.d/archive.conf`](deploy/nginx/conf.d/archive.conf):

```nginx
location /reports/ {
    proxy_pass http://reports:8001/;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

3. Redeploy:

```powershell
docker compose up -d --build proxy reports
```

Users access the new service at `http://<host>/reports/`.

## HTTPS (when domain is available)

1. Obtain certificates (e.g. certbot or your CA)
2. Copy [`deploy/nginx/conf.d/ssl.conf.example`](deploy/nginx/conf.d/ssl.conf.example) to `ssl.conf`
3. Mount certificates into the `proxy` service
4. Expose port `443` in `docker-compose.yaml`

## Troubleshooting

| Problem | Check |
|---------|-------|
| 404 on `/documents` | Use `/archive/documents` in production |
| Login loop | Cookie path — ensure `APP_BASE_PATH=/archive` matches Nginx |
| Upload fails | Nginx `client_max_body_size` in `deploy/nginx/nginx.conf` |
| DB connection error | `DATABASE_URL` must use host `db` inside Docker |
| Permission denied on uploads (Windows) | Check folder permissions on `UPLOAD_HOST_PATH` |

## Service URLs

| Environment | URL |
|-------------|-----|
| Production | `http://<host>/archive/documents` |
| Dev (no proxy) | `http://localhost:8000/documents` |
| Health | `http://<host>/health` |
