# Database migrations

Alembic revision IDs are independent of the application release version.
This file maps service releases to the migration chain they include.

The API **does not** create tables on startup. Apply migrations before using the service:

```bash
docker compose exec api alembic upgrade head
```

## Release mapping

| Service version | Migration file | Description |
|---------------|----------------|-------------|
| (initial) | `8a7eb69bb820_init_schema.py` | Initial schema with document status workflow |
| — | `b1c2d3e4f5a6_add_user_org_and_projects.py` | User preferred org and projects |
| 0.7.0 | `c2d3e4f5a6b7_v0700_notifications_and_columns.py` | Notifications and column preferences |
| — | `d3e4f5a6b7c8_doc_review_comment_and_register_flag.py` | Review comment and registration notification flag on documents |
| **0.10.0** | `b2c3d4e5f6a7_v1000_file_upload_event.py` | Document change log, ИИ, file revisions, status workflow (current head) |

### 0.8.0

- **Service version:** 0.8.0
- **Migration:** `e4f5a6b7c8d9_add_document_delete_notification_type.py`
- **Description:** Added `document_delete` notification event type; no new tables or endpoints in this migration.
