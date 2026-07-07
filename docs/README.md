# Documentation

## Administration scripts

The `scripts/` directory contains utilities for manual database management. They are not run automatically at application startup.

### `promote_user.py` — assign a user role

Changes the `role` of an existing user in the `users` table.

#### Roles

| Role | Description |
|------|-------------|
| `user` | Upload documents, work with own records |
| `reviewer` | Review documents, change status |
| `admin` | Full access, delete documents, edit metadata |

#### Usage

```bash
python scripts/promote_user.py <login> <role>
```

---

## Running from Docker (recommended)

```bash
docker compose up -d
docker compose exec api python scripts/promote_user.py ivanov admin
```

---

## HTTPS and browser push notifications

Browser push requires a **secure context** (HTTPS or `localhost`). The stack ships with nginx terminating TLS on port **8443** by default (mapped to container 443).

### First-time setup

1. Start services: `docker compose up -d`
2. On first proxy start, a **self-signed certificate** is created in `nginx/certs/` if missing
3. Open **https://localhost:8443/archive/** and accept the browser certificate warning
4. Configure VAPID keys (see root [README.md](../README.md))

### Access from Windows when Docker runs in WSL2

WSL2 often does **not** forward port 8443 to Windows `localhost`. Two options:

**Option A (simplest): use HTTP on localhost**

Browsers treat `http://localhost` as a secure context — **push works without HTTPS**:

```text
http://localhost/archive/
```

From Windows PowerShell:

```powershell
curl http://localhost/archive/documents
```

**Option B: forward ports to WSL**

Run as Administrator on Windows:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\windows-forward-ports.ps1
```

Then open `https://localhost:8443/archive/` or use Option A.

You can also enable mirrored networking in `%UserProfile%\.wslconfig`:

```ini
[wsl2]
networkingMode=mirrored
```

Then run `wsl --shutdown` and restart WSL.

### LAN access (https://192.168.x.x:8443)

Docker in WSL2 listens inside the WSL VM. The Windows LAN IP (e.g. `192.168.4.108`) does **not** forward to WSL automatically.

**On the Windows host**, run as Administrator:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\windows-forward-ports.ps1
```

Add the server LAN IP to the certificate (optional, reduces browser warnings):

```env
SSL_CERT_CN=SERVER-PDM
SSL_CERT_IP=192.168.4.108
```

Regenerate cert and restart proxy:

```bash
rm -f nginx/certs/*.pem
docker compose up -d --build proxy
```

Test from another PC:

```text
https://192.168.4.108:8443/archive/
```

Push over LAN requires HTTPS (not plain `http://192.168.x.x`).

### «Подключение не защищено» / crossed-out HTTPS

This is **normal for a self-signed certificate**. The connection is encrypted, but the browser does not trust the issuer until you install the certificate.

**Step 1 — regenerate with hostname and LAN IP in the certificate**

In `.env` on the server:

```env
SSL_CERT_CN=SERVER-PDM
SSL_CERT_IP=192.168.4.108
```

```bash
rm -f nginx/certs/*.pem
docker compose up -d --build proxy
```

Check SAN in logs: `DNS:SERVER-PDM, DNS:localhost, IP:127.0.0.1, IP:192.168.4.108`

**Step 2 — trust the certificate on each client PC (Windows)**

Copy `nginx/certs/fullchain.pem` from the server, then run **as Administrator**:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\trust-cert-windows.ps1 -CertPath C:\Temp\fullchain.pem
```

Restart the browser. The address bar should show a normal padlock.

**Alternative:** open by hostname `https://SERVER-PDM:8443/archive/` (add `192.168.4.108 SERVER-PDM` to `hosts` on clients if there is no DNS).

Without Step 2, users can still click «Advanced» → «Proceed» — push will work, but the warning remains.

---

Set your server hostname or IP in `.env`:

```env
SSL_CERT_CN=SERVER-PDM
```

Regenerate the certificate:

```bash
rm -f nginx/certs/*.pem
docker compose up -d proxy
```

Or use the helper script on the host (requires OpenSSL):

```bash
SSL_CERT_CN=SERVER-PDM ./scripts/generate-ssl-cert.sh
docker compose up -d proxy
```

Port 80 redirects to HTTPS on port 8443. Push will not work when accessing the site as `http://192.168.x.x/...` without HTTPS.

If connection is refused on port 443, use **8443** (default) or set `HTTPS_PORT` in `.env`.

### VAPID keys

Generate inside the API container:

```bash
docker compose exec api python -m py_vapid --applicationServerKey
```

Add to `.env`:

```env
VAPID_PUBLIC_KEY=<Application Server Key>
VAPID_PRIVATE_KEY=/app/private_key.pem
VAPID_SUBJECT=mailto:admin@example.com
```

Restart: `docker compose up -d api`

Users enable push in **Profile** → **Connect push** and choose event types.

---

## Document file naming

When a file is uploaded, if its base name does not match the registered designation, it is **physically renamed** on disk and in the database to:

```text
{designation} ({original_basename}){extension}
```

Example: designation `ABCD.123456.001`, uploaded file `drawing.pdf` → `ABCD.123456.001 (drawing).pdf`.

If the file name already matches the designation (e.g. `ABCD.123456.001.pdf`) or the `{designation} ({basename})` pattern, no rename is applied.

---

## Migrations

```bash
docker compose exec api alembic upgrade head
```

From the host, use `ALEMBIC_DATABASE_URL` pointing to `localhost` (see comments in `.env.example`).

---

## Changelog

Release notes are available at `/archive/changelog` (from the **changelog** link next to the version in the page header). The page lists versions from the current release onward.
