# Changelog

All notable changes to this project are documented here.
Version numbers follow [Semantic Versioning](https://semver.org/) (`MAJOR.MINOR.PATCH`).

## 0.26.2

- **Administration — mailing:** new «Рассылка» section; broadcast to all verified users moved here from «Пользователи».
- **Administration — scheduled mailing:** cron-based emails to manually listed addresses with a custom signature, subject, and body (runs in the API process using the app timezone).
- **Administration — scheduled mailing stop date:** optional end date; after that day the schedule turns off automatically.

## 0.26.1

- **Locale — dates:** date fields again use the Russian calendar and `ДД.ММ.ГГГГ` (instead of the browser-native English `MM/DD/YYYY` picker).
- **Locale — file upload:** the file chooser button label is «Выберите файл» regardless of browser language.
- **Orders:** opening an order from the Приказы tab no longer fails with SQLAlchemy `unique()` / joined eager-load error.
- **Headers:** ТУ, ИИ, and order view/edit pages use the same blue header styling as the rest of the archive.
- **CI:** backup and OCR sidecar tests no longer collide on the bare module name `main` (unique `importlib` loads).

## 0.26.0

- **Electronic specification (GOST 2.055 / 2.106):** GOST-based detection of specification pages and `document_role` in OCR geometry (`standalone_specification`, `assembly_with_spec_pages`, `combined_a4`, `assembly_drawing`).
- **Archive model:** `is_specification`, `contains_embedded_specification`, SB↔spec links (`specification_document_id`, `assembly_document_id`), table `specification_entries` with GOST sections.
- **OCR commit:** separate SB + spec records with split PDF for multi-page files; combined A4 saves one SB with embedded spec; auto-draft records (`auto_draft` status) for unmatched spec rows.
- **Document card:** «Спецификация» block for СБ (find by designation from card, link with «Это спецификация»); «Состав спецификации» grouped by section.
- **Permissions:** `link_specification` in role matrix (defaults mirror document links).
- **Dataset export:** `spec_ground_truth` in labels JSON for future ML on specifications.
- **Doc kind cleanup:** removed `СП` from KD kind codes; electronic specifications use `is_specification` only.
- **OCR batch workflow:** after «Принять и создать документ» or «Сохранить как учебный пример» you return to the batch page; accepted jobs show status «Принят» / «Принят (учебный)».

## 0.25.2

- **Administration — backups history:** automatic backups now appear in history. Listing no longer fails when `schedule.json` sits next to backup folders; records sync from the backup agent and removed batches are pruned from the UI history.
- **Administration — backup retention:** cleanup always keeps the newest backup batch so the last remaining backup is never deleted automatically when older batches are purged.
- **Administration — backups UI:** history table refresh works again; saving the schedule no longer resets retention days to 30.

## 0.25.1

- **Alembic:** restored missing revision `s9t0u1v2w3x4` (specification schema) so API startup no longer fails with `Can't locate revision identified by 's9t0u1v2w3x4'` after a database was upgraded during the 0.26.0 preview branch.
- **OCR commit — push resilience:** web push transport errors (DNS/network to FCM) no longer abort document creation from OCR commit or uploads; failures are logged and skipped.
- **OCR review — multiple products:** on the verification screen you can assign additional products from the same project (applicability) alongside the primary product.
- **OCR — multi-page SB / specification:** multi-page PDFs are scanned for specification sheets; recognized designations are suggested on the review screen with a link picker to attach referenced archive records at commit time.
- **Document delete:** clearing `ocr_jobs.document_id` before delete fixes FK violation when removing a record created from OCR.
- **OCR documents — `auto_recognized`:** documents committed from OCR are stored with `auto_recognized = true`; manually registered records remain `false`.
- **OCR review — file and pages:** open the uploaded source file from the review screen; browse all pages of multi-page PDFs with prev/next navigation.
- **OCR review — selection UX:** selected applicability products and document links are highlighted in green; all project products are shown in applicability cards including the primary product.
- **Document card — applicability:** the applicability section lists the primary product plus additional applicability entries.
- **OCR upload — 504 fix:** file upload returns immediately; OCR runs in the background per batch. Nginx `proxy_read_timeout` defaults to 600s. Batch page auto-refreshes while processing.

## 0.25.0

- **OCR phases 1–3:** isolated OCR sidecar, stamp/cell recognition, review/commit, annotation UI, format-bound ROI templates, signatures, training examples, dataset ZIP export, and optional stamp detector. See `docs/ocr/README.md` and `docs/ocr/PHASE3.md`.
- **OCR — higher DPI:** default render DPI **400** (`OCR_RENDER_DPI`); page preview max side **2800**.
- **OCR — stamp region per format:** annotate title-block area on the page preview; `stamp_roi_norm` stored in `ocr_format_templates` (A4 vs A3).
- **OCR — format-bound cell ROI templates:** cell boxes reused per paper format; format dropdown coerced to ISO codes (Cyrillic «А» → Latin «A»).
- **OCR — review UX:** org/FIO suggestion chips, date normalization (`YYYY-MM-DD` / `dd.mm.yy`), doc-kind from designation (incl. Latin aliases), signature ink detection, per-cell ROI thumbnails, «учебный пример», discard keeps markup.
- **OCR phase 3 — dataset / detector:** `/ocr/dataset` ZIP export; `ocr/training/` YOLO + DVC/MLflow stubs; optional `OCR_STAMP_DETECTOR_PATH`.

## 0.24.1

- **Administration — containers:** ops-agent now discovers all services in the current Docker Compose project dynamically (no hard-coded whitelist). Service names are read from the `com.docker.compose.service` label instead of parsing container names. Container status on the dashboard and containers page auto-refreshes every 15 seconds.

## 0.24.0

- **Technical specifications (ТУ):** register ТУ by OKPO from the «Ещё» menu using the format OKPD2-product-serial-OKPO-year (e.g. `26.20.13-002-95979699-2024`). New «ТУ» tab on the main archive page with filters, column visibility in the profile, and record cards with preview/download.
- **Projects — establishing TU:** administrators can attach a registered ТУ to a project (same pattern as establishing orders).
- **Password recovery:** reset links in email always use HTTPS, even when the forgot-password form was submitted over HTTP.
- **Profile — change password:** change password from the personal account with current password verification; optional «send link to email» reuses the forgot-password flow.
- **Orders — metadata:** orders can be linked to a project and multiple products; editable on the order metadata edit page. Project and product columns added to the orders list.

## 0.23.2

- **Profile — column visibility:** saving column checkboxes in the personal account now persists correctly (SQLAlchemy JSON column change detection).
- **Profile — push notifications:** removed separate «Подключить push» / «Отключить push» buttons and the duplicate «Включить push-уведомления» checkbox; the status banner is now a single toggle button.
- **Profile — actions:** «Сохранить» and «Вернуться» buttons are larger, centered, separated by a divider, and placed lower for better visibility.
- **Filters:** «Сохранить фильтры» checkbox is vertically aligned with «Применить фильтры» and «Сбросить».
- **Documents and notifications lists:** added a «Загрузить ещё 100» button next to the default load-more control for bulk pagination.

## 0.23.1

- **Applicability — verify/propagate fix:** child records are checked only by explicit applicability entries (not by their own product assignment). When syncing from a parent, applicability entries are created even when the target product matches the child's own product, so linked records show parent applicability in the card block.

## 0.23.0

- **Links — applicability sync:** when an outgoing link is added, the parent record's applicability is propagated to the linked record and its branches (BFS) with file copying. When a link is removed, parent applicability entries are cleared from the unlinked target and its subtree (records still reachable via other links are kept). A blocking progress overlay is shown during link add/remove operations.

## 0.22.0

- **Applicability — verify children:** the document card applicability block has a «Проверить применяемость дочерних записей» button that runs a BFS pass over all outgoing link branches and adds any missing parent applicability entries to child records (children may have additional applicability beyond the parent's). Child traversal uses link target IDs directly; each child record is reloaded before updating. Clearer result messages when there are no links or updates fail (e.g. missing files).
- **Filters — session persistence:** the «Сохранить фильтры» label is placed to the right of the checkbox on the same line, vertically aligned with the filter action buttons.
- **Add document form:** removed the default caption «Выберите тип записи для регистрации в архиве.»

## 0.21.0

- **Applicability — propagation to links:** when applicability is added to a record, all documents reachable via outgoing links (not backlinks) are traversed to the end of each branch (BFS); if a linked record is missing applicability entries, they are added automatically with file copying. A blocking overlay with a progress animation is shown while the operation runs.
- **Applicability modal:** product names are clickable (not only checkboxes); selected products are highlighted in green.
- **Filters — session persistence:** the checkbox label is renamed to «Сохранить фильтры», shown in gray to the right of the checkbox.

## 0.20.0

- **Documents page — tabs:** the main archive list is split into three tabs: «КД и ТД», «Извещения», and «Приказы». Each tab has its own filters, column visibility settings in the profile, and record cards with actions and preview.
- **Register notifications and orders:** new records can be created from the «Добавить новый документ» block via the «Ещё» menu (under the КД/ТД buttons). Notification and order numbers must be unique across the archive.
- **Formal changes (apply-change):** when applying a formal change to an approved КД/ТД record, select a registered change notification from the archive instead of uploading a new ИИ file. The notification card shows which projects and products use that ИИ.
- **Applicability:** multiple products can be selected at once when adding applicability; the applicability list on the document card is collapsed by default when entries exist.
- **Projects — establishing order:** administrators can assign a registered order as the project's establishing document; otherwise gray text «Устанавливающий документ не выбран» is shown.
- **Filters — session persistence:** a «Сохранить в сессии» checkbox next to «Сбросить» stores filter values in the browser session until the tab is closed.
- **Administration — backups:** backup history syncs immediately after a manual backup; the list auto-refreshes on the backups page. A new section configures how many days to keep old backups before automatic deletion.

## 0.19.1

- **Metadata editing:** the edit form now allows changing all person names (developer, reviewer, approver), all signature dates, and the document title. Known names can be selected from a dropdown, matching the registration form.
- **File replace on metadata edit:** the metadata edit form includes an optional file upload — you can attach a new file or replace the existing one without leaving the edit page. For first-time upload, document format is required.
- **File rename on title change:** when the document title is changed without uploading a new file, the stored file is renamed according to the archive naming rules (`{designation} - {title}` or `{designation} ({basename}) - {title}`).

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
