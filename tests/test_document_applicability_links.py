import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.document_applicability import (
    add_document_applicability,
    copy_document_to_project,
    get_available_applicability_projects,
)
from app.document_links import add_document_links, search_documents_by_designation
from app.models import BaseDocument, DesignDocument, DocumentApplicability, Project


def _doc_with_file(project_id: int = 1) -> BaseDocument:
    doc = BaseDocument(id=10, type="DD", project_id=project_id, file_name="A.pdf", file_path="/tmp/A.pdf")
    doc.design_document = DesignDocument(designation="TEST.000001.001СБ", doc_kind_code="СБ")
    doc.project = Project(id=project_id, name="Source", slug="source")
    return doc


def test_copy_document_to_project(tmp_path):
    source_file = tmp_path / "source.pdf"
    source_file.write_bytes(b"pdf-content")
    doc = _doc_with_file()
    doc.file_path = str(source_file)
    target = Project(id=2, name="Target", slug="target-project")

    with patch("app.document_applicability.UPLOAD_DIR", str(tmp_path)):
        target_path, file_name = copy_document_to_project(doc, target)

    assert os.path.exists(target_path)
    assert file_name == "A.pdf"
    assert "target-project" in target_path
    assert os.path.sep + "СБ" + os.path.sep in target_path


@pytest.mark.asyncio
async def test_add_document_applicability_rejects_same_project():
    session = AsyncMock()
    session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None)))
    session.get = AsyncMock()
    doc = _doc_with_file(project_id=5)

    with pytest.raises(HTTPException) as exc:
        await add_document_applicability(session, doc, 5, 1)
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_add_document_links_rejects_self_reference():
    session = AsyncMock()
    doc = _doc_with_file()
    with pytest.raises(HTTPException) as exc:
        await add_document_links(session, doc, [doc.id], 1)
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_get_available_applicability_projects_excludes_current_and_used():
    doc = _doc_with_file(project_id=1)
    projects = [
        Project(id=1, name="Current", slug="current"),
        Project(id=2, name="Free", slug="free"),
        Project(id=3, name="Used", slug="used"),
    ]
    session = AsyncMock()

    async def execute_side_effect(stmt):
        result = MagicMock()
        stmt_str = str(stmt)
        if "document_applicability.project_id" in stmt_str:
            result.all.return_value = [(3,)]
        else:
            scalars = MagicMock()
            scalars.all.return_value = projects
            result.scalars.return_value = scalars
        return result

    session.execute = AsyncMock(side_effect=execute_side_effect)
    available = await get_available_applicability_projects(session, doc)
    assert [p.id for p in available] == [2]
