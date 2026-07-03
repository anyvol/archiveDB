# Changelog

All notable changes to this project are documented here.
Version numbers follow [Semantic Versioning](https://semver.org/) (`MAJOR.MINOR.PATCH`).

## 0.13.1

- OTP entry pages (email verification and password reset): buttons stacked vertically in a single card.
- Password reset via 6-digit email code instead of a link; after entering a new password, redirect to login with «Новый пароль установлен» message (no JSON response).
- Documents archive page loads 20 records at a time with a «Загрузить ещё 20» button.
- Fixed OTP/email verification redirect: use HTTP 303 so the browser opens login page instead of re-POSTing the form (JSON validation error).
- Uploaded file name includes registration title: `{designation} ({original}) - {doc_name}.ext`, or `{designation} - {doc_name}.ext` when the file base name matches the designation.
- LAN access: nginx serves `http://<server-ip>/archive/` directly (no HTTPS redirect); use `https://<ip>:8443/archive/` for push (port 443 is not used by default).

## 0.13.0

- Added **master_admin** role and **Администрирование** section in the header (containers/logs, users, traffic, timezone, backups, SMTP).
- Separate **backup** and **ops-agent** Docker services; backups stored via `BACKUP_HOST_PATH` (supports Windows host paths from WSL, e.g. `/mnt/c/ArchiveDB/backups`).
- **Mandatory email** at registration with 6-digit verification code sent via SMTP.
- **Password reset** via email link; mailer configurable in admin panel or `.env`.
- New tables: `system_settings`, `email_verification_codes`, `password_reset_tokens`, `backup_records`.
- Alembic migration `f6a7b8c9d0e1` (idempotent where possible).

## 0.12.2

- Fixed project documents not appearing in «Проекты» when a development order was uploaded at project creation: the file was saved to «Прочие документы» on disk but not registered in `project_files`.
- Opening a project page now syncs existing files from the «Прочие документы» folder into the project documents list (repairs projects created before this fix).

## 0.12.1

- Fixed document deletion failing with a database integrity error when the document had change log entries (`document_change_events`, `file_revisions`, or `change_notifications`).
- Document deletion now sends a notification to all users (except the person who deleted the record); delete notifications are saved to the «Уведомления» list and browser push is sent only after a successful delete.
- Registration error for duplicate serial number renamed to «Указанный порядковый номер уже используется».
- Added departments «Отдел интеграции и сопровождения» and «Сервисный отдел» to registration and profile forms.
- Personal cabinet shows the user's role in the system (read-only).

## 0.12.0

- Any authenticated user can upload a file to a record that has no file yet.
- Context menu: «Запрос на исправление» for documents «На проверке» with an uploaded file.
- Document registration form: expanded metadata section (ФИО and dates), larger input, picker for existing names/surnames from the database.
- Create button centered, enlarged, renamed to «Создать запись и перейти к загрузке файла ЭД».
- Upload page: drag-and-drop area height doubled; required «Формат документа» field (A0–A5 and composite formats).
- On file selection, page size is read from PDF/image metadata when possible and the format is auto-filled with a notice.
- New «Проекты» section in the header: list projects, add projects with description and photos, attach project documents, download files.
- Project photos stored under `{project_slug}/изображения/` on the server.
- Database: `documents.document_format`, `projects.description`, `projects.created_at`, tables `project_files` and `project_images`.
- Alembic migration `c3d4e5f6a7b8` (idempotent).
- Docker: API container applies migrations automatically on startup (`scripts/docker-entrypoint.sh`).
- Schema repair script `scripts/ensure_schema.py` fixes missing 0.12.0 columns when Alembic reports head without applying DDL.
- Document registration metadata: separate fields for developer, date, reviewer, and approver; compact inputs with «choose from existing» per field (single FIO, replaces value).
- Signature dates: developer, reviewer, and approver (`developer_signed_date`, `reviewer_signed_date`, `approver_signed_date`).
- Create form returns JSON redirect for reliable navigation to upload page; org check no longer shows raw JSON messages.
- Name picker tooltip on hover instead of visible «Выбрать из существующих» label.
- Signature date fields use hover tooltips instead of visible labels.
- Header: «Проекты» link placed after «Уведомления».
- Uploaded file rename rule: `{designation} ({original_name}).{ext}` (space before parentheses).

## 0.10.0

- Status «Проверено» renamed to «Утверждено» (`approved`).
- Document record card (`/documents/{id}`): status, PDF/image preview, electronic change log, actions.
- Double-click or context menu «Открыть запись» opens the record card.
- GOST 2.503-2013 change workflow for КД and ТД:
  - Cosmetic file replace only when status is «Требуется исправление»; previous file kept in project `versions/` folder.
  - «Запрос на исправление» while «На проверке» for minor fixes (any user); reviewer can approve or reject.
  - «Внести изменения в документ» for approved records: ИИ upload, new file, change number/date, signature checkboxes.
  - Change notifications (ИИ) stored in project `Извещения об изменении/` folder.
- New tables: `document_change_events`, `change_notifications`, `file_revisions`.
- Preview endpoints for documents and ИИ (inline PDF/images).
- Alembic migration `a1b2c3d4e5f6` is idempotent (safe to re-run if tables were created by app startup).
- Removed `create_all` on API startup — use Alembic only (`alembic upgrade head`).
- Fixed PDF preview for files with non-ASCII names (Cyrillic in `Content-Disposition`).
- Changelog page shows full history from `CHANGELOG.md`; header aligned with other pages.
- Apply-change form: separate II number and change revision number (1, 2, 3…).
- Change log records file uploads and all status transitions.
- Filename must match current document on formal change; signature validation message improved.
- Help section updated for 0.10.0 workflow.

## 0.9.3

- Renamed uploaded files now keep the original extension at the end: `{designation}({basename}){ext}`.
- Notifications page loads 20 items at a time with a “Load more” button.
- Added project overview to the repository README.
- Help for new users opens in a new browser tab.
- Name and position fields cannot consist of digits only.
- Improved OKPO and push-notification checkbox alignment in the profile.
- Confirmation dialog when continuing without upload while a file is selected.
- Consistent header title size across all pages.

## 0.9.1

- Default HTTPS port is **8443** (port 443 is often blocked on WSL/Windows).
- HTTP on **localhost** serves the app directly (no redirect) — push works at `http://localhost/archive/`.
- Document files are now physically renamed on upload to `{designation}({filename})` when the file name does not match the record designation.
- Header link text changed from «изменения» to «changelog».
- Updated documentation (HTTPS, VAPID keys, file naming).

## 0.9.0

- Browser push notifications with per-event settings in the user profile.
- Changelog link next to the version number in the page header.
- Warning on document upload when the file name does not match the registered record designation.
- Dynamic context menu (right-click on a table row) for document actions in the archive list, with updated action labels.

## 0.8.0

- Switched versioning from `0.XXX` to Semantic Versioning (`MAJOR.MINOR.PATCH`).
- Single source of truth for the release version: `VERSION` file in the repository root.
- Added `GET /version` endpoint returning the current service version.
- CI validates `VERSION` format and builds a Docker image tagged with the release version.
