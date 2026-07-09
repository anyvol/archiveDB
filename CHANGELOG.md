# Changelog

All notable changes to this project are documented here.
Version numbers follow [Semantic Versioning](https://semver.org/) (`MAJOR.MINOR.PATCH`).

## 0.19.0

- **Record card — backlinks:** after the «Ссылки» block, the card shows «Обратные ссылки» — records that reference the current document (automatically derived from incoming links).
- **Record card — actions:** all commands from the archive context menu are available on the card, including «Удалить запись» for administrators.
- **Administration — role permissions:** new «Права доступа» page to configure function access per role (`user`, `reviewer`, `admin`); `master_admin` always has full access.
- **Administration — automatic backups:** configure scheduled backups by cron expression or interval (hours), with separate toggles for database and file backups; settings are stored in the database and applied to the backup service.
- **Admin broadcast email:** fixed routing so mass email (`/admin/users/broadcast-email`) no longer conflicts with the user update route.
- **Header menu:** added «Документы» link before «Администрирование».

## 0.18.1

- **Project archive download:** fixed a 500 error when downloading archives for projects whose slug contains non-ASCII characters (Cyrillic in `Content-Disposition`).
- **Applicability modal:** added separate project and product selectors with placeholders «Выберите проект» and «Выберите изделие»; the product list updates when a project is selected.
- **Applicability on record card:** each entry shows project and product as separate labeled fields.
- **Documents list:** added «Изделие» filter and table column (hideable in profile); the column lists all related products, and filtering matches applicability as well as the record's own product.

## 0.18.0

- **Products (изделия):** projects can contain multiple products with unique names per project. Products are managed on the project detail page in the «Проекты» section.
- **Server folder structure:** archive files are stored as `{project}/{product}/…` instead of `{project}/…`. Document kind subfolders, `versions/`, and «Извещения об изменении» are created inside the product folder.
- **New records:** when registering a document, select a product from the project list; when creating a new project inline, specify the first product name. If no product exists yet, create one in «Проекты».
- **Applicability (GOST 2.501-2013):** applicability now targets products, not projects. Copied files go to the target product folder.
- **Existing records:** records already in the database keep working with legacy paths until a product is assigned manually; move files on the server into the corresponding product folder when assigning products to old records. Previous applicability entries were cleared during migration and must be re-added per product.

## 0.17.1

- **Header menu:** extended the hover zone so the menu stays open when moving the pointer to menu items; clicking the menu button keeps it open until you click elsewhere.
- **Notifications:** moved the bell icon further left so it is not covered by the menu hover area.

## 0.17.0

- **Header menu:** navigation links moved into a hover menu on the right; the signed-in user is shown as «Вы вошли как {ФИО}», logout is labeled «Выйти».
- **Notifications:** removed from the menu; a bell icon with unread count in parentheses appears next to the menu button.
- **Home icon:** doubled in size in the header.
- **Version tag:** the changelog link was removed; clicking the version opens the changelog page.
- **Applicability (GOST 2.501-2013):** records can be applied to other registered projects; applicability is stored in the database, shown on the document card, and the file is copied into the target project folder. Admins can remove applicability. Adding applicability writes to the change log and sends a notification without changing document status.
- **Project archive download:** admins can download all files of a project as a ZIP archive preserving folder structure; the archive name includes formation date and project id.
- **Document links:** document cards show linked records; any role can add links via search by designation with confirmation; admins can remove links. Adding links sets the source record status to «На проверке», writes to the change log, and sends a notification.

## 0.16.0

- **File naming on upload:** if the uploaded base name differs from the designation, store as `{designation} ({original_basename}) - {doc_name}{extension}`; if it matches, store as `{designation} - {doc_name}{extension}`.
- **Date and time display:** registration date, last update, change log entries, and notification timestamps now show `DD.MM.YYYY HH:MM` in the timezone configured in the admin panel.
- **Header navigation:** the same links appear in the same order on every page; the «Архив документов» nav link was removed in favor of a home icon to the left of the page title.
- **Notifications:** clicking a notification opens the corresponding document card when the record still exists.
- **Archive list pagination:** the main documents page loads 20 records at a time with a «Загрузить ещё» button, like notifications.

## 0.15.2

- **Dates:** user-facing dates now render as `DD.MM.YYYY` and use the timezone selected in the admin panel.
- **Document filters:** registration and update date filters use native calendar inputs and timezone-aware local day ranges.
- **Document card:** redesigned the record card into readable sections with metadata, formal change rows, registration data, file information, and right-aligned approve/download actions.
- **Preview:** doubled the vertical size of the document preview frame.

## 0.15.1

- **Sliding session:** the `access_token` JWT cookie is refreshed on each authenticated request while the user remains active, using `ACCESS_TOKEN_EXPIRE_MINUTES` for both token lifetime and cookie `max_age`.
- **Expired session UX:** missing or expired sessions return a clear «Сессия истекла» message (`401` JSON with `detail: session_expired` for AJAX, redirect to `/login?expired=1` for HTML) instead of Pydantic validation errors on `/login`.
- **AJAX auth:** document creation and related `fetch` calls use `redirect: manual` and shared `SessionAuth` helpers so requests no longer follow redirects to the login form.

## 0.15.0

- **Document registration — execution suffix (КД only):** optional «Исполнение» field before the document kind code when registering design documentation; user enters digits from 1 to 99 (e.g. `1` → `-01`, `15` → `-15`) and the suffix is included in the designation preview and stored designation. Not available for technological documentation.
- **Designation uniqueness:** documents with the same serial number but different execution or document kind code are treated as distinct designations and can be registered separately (e.g. `ФЕТР.000000.001-01` vs `ФЕТР.000000.001-02`, or `ФЕТР.000000.001СБ` vs `ФЕТР.000000.001ГЧ`).
- Duplicate registration now reports «Указанное обозначение уже используется» when the full designation collides.

## 0.14.0

- **Administration — users:** delete user (context menu, confirmation); send email to one user or broadcast to all verified emails; generate one-time admin access code (15 min) for new users awaiting first login.
- **Administration — traffic:** dashboard with user, document, project, and file counts.
- **Administration — backups:** list remote backup batches and sync metadata into the admin UI.
- **Administration — containers:** list running Docker containers (when ops-agent is configured).
- **Administration — messaging:** broadcast email to all users with verified email addresses.
- **Email verification:** registration requires email verification before first login; resend verification from login page.
- **Password reset:** forgot-password flow with email link.
- **Admin access code:** optional global access code gate for admin routes (`ADMIN_ACCESS_CODE`).

## 0.13.3

- Fixed HTTP 413 when creating a document with an attached project development-order file (nginx `client_max_body_size` and FastAPI upload limits aligned).

## 0.13.0

- **Administration panel:** user list, role management, traffic stats, backup sync, container list, broadcast email.
- **Email verification** and **password reset** flows.
- **Backups** service and ops-agent integration.
- Alembic migrations for admin-related tables.

## 0.12.2

- **Projects UI:** project detail page lists documents linked to the project (previously missing due to relationship loading).

## 0.12.1

- **Document delete:** fixed error when deleting records with linked notifications or file paths.

## 0.12.0

- **Upload permissions:** refined who can upload/replace files by status and role.
- **Metadata UI:** improved document registration form and profile preferences.
- **Document format** helpers and **projects** section enhancements.

## 0.11.0

- Document metadata editing, column preferences, and UI polish.

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

## 0.9.2

- Push notifications (Web Push) with user preferences in profile.
- Session and auth improvements.

## 0.9.1

- HTTPS support for push notifications.
- File rename rule fix and documentation updates.

## 0.9.0

- Notifications system, document list filters, and registration workflow updates.

## 0.8.0

- Initial governed document workflow and project support.

## 0.7.1

- Bug fixes and deployment improvements.

## 0.7.0

- Core archive: users, documents, projects, file storage.
