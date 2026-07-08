import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.document_applicability import (
    add_document_applicability,
    copy_document_to_product,
    get_available_applicability_products,
)
from app.document_links import add_document_links, search_documents_by_designation
from app.models import BaseDocument, DesignDocument, DocumentStatus, Product, Project, User, UserRole


def _doc_with_file(project_id: int = 1, product_id: int = 10) -> BaseDocument:
    doc = BaseDocument(
        id=10,
        type="DD",
        project_id=project_id,
        product_id=product_id,
        file_name="A.pdf",
        file_path="/tmp/A.pdf",
    )
    doc.design_document = DesignDocument(designation="TEST.000001.001СБ", doc_kind_code="СБ")
    doc.project = Project(id=project_id, name="Source", slug="source")
    doc.product = Product(id=product_id, project_id=project_id, name="Изделие A", slug="product-a")
    return doc


def test_copy_document_to_product(tmp_path):
    source_file = tmp_path / "source.pdf"
    source_file.write_bytes(b"pdf-content")
    doc = _doc_with_file()
    doc.file_path = str(source_file)
    target_project = Project(id=2, name="Target", slug="target-project")
    target = Product(id=20, project_id=2, name="Изделие B", slug="product-b", project=target_project)

    with patch("app.document_applicability.UPLOAD_DIR", str(tmp_path)):
        target_path, file_name = copy_document_to_product(doc, target)

    assert os.path.exists(target_path)
    assert file_name == "A.pdf"
    assert "target-project" in target_path
    assert "product-b" in target_path
    assert os.path.sep + "СБ" + os.path.sep in target_path


@pytest.mark.asyncio
async def test_add_document_applicability_rejects_same_product():
    session = AsyncMock()
    session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None)))
    session.get = AsyncMock()
    doc = _doc_with_file(project_id=5, product_id=5)
    user = User(id=1, login="tester", password_hash="x", role=UserRole.user)

    with pytest.raises(HTTPException) as exc:
        await add_document_applicability(session, doc, 5, user)
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_add_document_links_rejects_self_reference():
    session = AsyncMock()
    doc = _doc_with_file()
    user = User(id=1, login="tester", password_hash="x", role=UserRole.user)
    with pytest.raises(HTTPException) as exc:
        await add_document_links(session, doc, [doc.id], user)
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_add_document_links_sets_pending_review_status():
    session = AsyncMock()
    source = _doc_with_file()
    source.status = DocumentStatus.approved
    target = BaseDocument(id=20, type="TD")
    target.tech_document = MagicMock(designation="TD.000001.001")
    target.design_document = None
    user = User(id=1, login="tester", password_hash="x")

    existing_result = MagicMock()
    existing_result.all.return_value = []

    found_result = MagicMock()
    found_result.all.return_value = [(20,)]

    target_docs_result = MagicMock()
    target_docs_result.scalars.return_value.unique.return_value.all.return_value = [target]

    session.execute = AsyncMock(side_effect=[existing_result, found_result, target_docs_result])
    session.add = MagicMock()
    session.flush = AsyncMock()

    with patch("app.document_links.log_change_event", new_callable=AsyncMock) as log_event, patch(
        "app.document_links.log_document_status_change", new_callable=AsyncMock
    ) as log_status, patch("app.document_links.notify_document_edit", new_callable=AsyncMock) as notify_edit:
        await add_document_links(session, source, [20], user)

    assert source.status == DocumentStatus.pending_review
    log_event.assert_awaited_once()
    log_status.assert_awaited_once()
    notify_edit.assert_awaited_once()


@pytest.mark.asyncio
async def test_add_document_applicability_logs_and_notifies_without_status_change(tmp_path):
    session = AsyncMock()
    source_file = tmp_path / "source.pdf"
    source_file.write_bytes(b"pdf-content")
    doc = _doc_with_file(project_id=1, product_id=10)
    doc.file_path = str(source_file)
    doc.status = DocumentStatus.approved
    project = Project(id=2, name="Target", slug="target")
    product = Product(id=20, project_id=2, name="Target product", slug="target-product", project=project)
    user = User(id=1, login="tester", password_hash="x", role=UserRole.user)

    existing_result = MagicMock()
    existing_result.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=existing_result)
    session.get = AsyncMock(return_value=product)
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()

    with patch("app.document_applicability.UPLOAD_DIR", str(tmp_path)), patch(
        "app.document_applicability.log_change_event", new_callable=AsyncMock
    ) as log_event, patch("app.document_applicability.notify_document_edit", new_callable=AsyncMock) as notify_edit:
        await add_document_applicability(session, doc, 20, user)

    assert doc.status == DocumentStatus.approved
    log_event.assert_awaited_once()
    notify_edit.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_available_applicability_products_excludes_current_and_used():
    doc = _doc_with_file(project_id=1, product_id=10)
    products = [
        Product(id=10, project_id=1, name="Current", slug="current"),
        Product(id=20, project_id=2, name="Free", slug="free"),
        Product(id=30, project_id=3, name="Used", slug="used"),
    ]
    session = AsyncMock()

    async def execute_side_effect(stmt):
        result = MagicMock()
        stmt_str = str(stmt)
        if "document_applicability.product_id" in stmt_str:
            result.all.return_value = [(30,)]
        else:
            unique = MagicMock()
            unique.all.return_value = products
            scalars = MagicMock()
            scalars.unique.return_value = unique
            result.scalars.return_value = scalars
        return result

    session.execute = AsyncMock(side_effect=execute_side_effect)
    available = await get_available_applicability_products(session, doc)
    assert [p.id for p in available] == [20]
