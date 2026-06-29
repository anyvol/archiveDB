# Changelog

All notable changes to this project are documented here.
Version numbers follow [Semantic Versioning](https://semver.org/) (`MAJOR.MINOR.PATCH`).

## 0.8.0

- Switched versioning from `0.XXX` to Semantic Versioning (`MAJOR.MINOR.PATCH`).
- Single source of truth for the release version: `VERSION` file in the repository root.
- Added `GET /version` endpoint returning the current service version.
- CI validates `VERSION` format and builds a Docker image tagged with the release version.
