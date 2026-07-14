# Electronic specification (OCR + archive)

See [README.md](./README.md) for the general OCR pipeline.

## Detection (GOST R 2.106-2019)

The sidecar classifies each upload with `document_role`:

| Role | Meaning |
|------|---------|
| `standalone_specification` | All pages are specification sheets |
| `assembly_with_spec_pages` | SB pages + separate spec pages → two archive records on commit |
| `combined_a4` | Spec table above title block on one A4 sheet → one SB record with `contains_embedded_specification` |
| `assembly_drawing` | No specification detected |

Markers: title «СПЕЦИФИКАЦИЯ», GOST section headers, table columns (Поз., Обозначение, Наименование, Кол., …).

## Archive

- **Specification record:** `is_specification=true`, designation **without** doc-kind suffix (e.g. `ФЕТР.301524.002`).
- **SB record:** `doc_kind_code=СБ`; optional `specification_document_id` or `contains_embedded_specification`.
- **Rows:** `specification_entries` with section, position, designation, name, quantity, optional `linked_document_id`.
- **Auto drafts:** unmatched rows can create records with status `auto_draft` («Создано автоматически, нужна информация»).

## Dataset

Exported ZIP `labels.json` includes `spec_ground_truth` (pages, rows, `document_role`) for future ML training.
