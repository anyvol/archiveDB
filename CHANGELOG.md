# Changelog

All notable changes to this project are documented here.
Version numbers follow [Semantic Versioning](https://semver.org/) (`MAJOR.MINOR.PATCH`).

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
