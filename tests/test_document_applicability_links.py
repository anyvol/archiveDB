import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.document_applicability import (
    add_document_applicability,
    add_document_applicability_many,
    build_applicability_modal_options,
    copy_document_to_product,
    get_available_applicability_products,
    propagate_applicability_to_outgoing_links,
    verify_child_applicability,
)
from app.document_links import (
    add_document_links,
    get_transitive_outgoing_document_ids,
    get_transitive_outgoing_documents,
    search_documents_by_designation,
)
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


def test_build_applicability_modal_options_groups_products_by_project():
    project_a = Project(id=1, name="Alpha", slug="alpha")
    project_b = Project(id=2, name="Beta", slug="beta")
    products = [
        Product(id=10, project_id=1, name="P-A1", slug="p-a1", project=project_a),
        Product(id=11, project_id=1, name="P-A2", slug="p-a2", project=project_a),
        Product(id=20, project_id=2, name="P-B1", slug="p-b1", project=project_b),
    ]

    options = build_applicability_modal_options(products)

    assert [item["name"] for item in options] == ["Alpha", "Beta"]
    assert options[0]["products"] == [{"id": 10, "name": "P-A1"}, {"id": 11, "name": "P-A2"}]
    assert options[1]["products"] == [{"id": 20, "name": "P-B1"}]


@pytest.mark.asyncio
async def test_get_transitive_outgoing_document_ids_traverses_all_branches():
    source = _doc_with_file()

    async def target_ids_side_effect(_session, document_id):
        if document_id == source.id:
            return [20, 40]
        if document_id == 20:
            return [30]
        return []

    session = AsyncMock()
    with patch("app.document_links.get_outgoing_link_target_ids", new_callable=AsyncMock, side_effect=target_ids_side_effect):
        collected = await get_transitive_outgoing_document_ids(session, source.id)

    assert collected == [20, 40, 30]


@pytest.mark.asyncio
async def test_get_transitive_outgoing_documents_traverses_all_branches():
    source = _doc_with_file()
    doc_b = _doc_with_file()
    doc_b.id = 20
    doc_c = _doc_with_file()
    doc_c.id = 30

    session = AsyncMock()
    with patch(
        "app.document_links.get_transitive_outgoing_document_ids",
        new_callable=AsyncMock,
        return_value=[20, 30],
    ), patch("app.document_workflow.fetch_document", new_callable=AsyncMock, side_effect=[doc_b, doc_c]):
        collected = await get_transitive_outgoing_documents(session, source.id)

    assert [doc.id for doc in collected] == [20, 30]


@pytest.mark.asyncio
async def test_propagate_applicability_to_outgoing_links_adds_missing():
    source = _doc_with_file(project_id=1, product_id=10)
    target = _doc_with_file(project_id=1, product_id=11)
    target.id = 20
    target.design_document = DesignDocument(designation="TEST.000002.001СБ", doc_kind_code="СБ")
    user = User(id=1, login="tester", password_hash="x", role=UserRole.user)

    product_id_calls = {"count": 0}
    session = AsyncMock()

    async def execute_side_effect(_stmt):
        result = MagicMock()
        product_id_calls["count"] += 1
        result.all.return_value = [(30,)] if product_id_calls["count"] == 1 else []
        return result

    session.execute = AsyncMock(side_effect=execute_side_effect)

    add_mock = AsyncMock()

    with patch(
        "app.document_applicability.get_transitive_outgoing_document_ids",
        new_callable=AsyncMock,
        return_value=[20],
    ), patch(
        "app.document_applicability.fetch_document",
        new_callable=AsyncMock,
        return_value=target,
    ), patch("app.document_applicability.add_document_applicability", add_mock):
        results = await propagate_applicability_to_outgoing_links(session, source, user)

    assert len(results) == 1
    assert results[0]["target_id"] == 20
    assert results[0]["success"] is True
    add_mock.assert_awaited_once_with(session, target, 30, user)


@pytest.mark.asyncio
async def test_propagate_applicability_uses_transitive_outgoing_documents():
    source = _doc_with_file(project_id=1, product_id=10)
    direct = _doc_with_file(project_id=1, product_id=11)
    direct.id = 20
    nested = _doc_with_file(project_id=1, product_id=12)
    nested.id = 30
    user = User(id=1, login="tester", password_hash="x", role=UserRole.user)

    product_id_calls = {"count": 0}
    session = AsyncMock()

    async def execute_side_effect(_stmt):
        result = MagicMock()
        product_id_calls["count"] += 1
        result.all.return_value = [(30,)] if product_id_calls["count"] == 1 else []
        return result

    session.execute = AsyncMock(side_effect=execute_side_effect)

    add_mock = AsyncMock()

    with patch(
        "app.document_applicability.get_transitive_outgoing_document_ids",
        new_callable=AsyncMock,
        return_value=[20, 30],
    ), patch(
        "app.document_applicability.fetch_document",
        new_callable=AsyncMock,
        side_effect=[direct, nested],
    ), patch("app.document_applicability.add_document_applicability", add_mock):
        await propagate_applicability_to_outgoing_links(session, source, user)

    assert add_mock.await_count == 2


@pytest.mark.asyncio
async def test_verify_child_applicability_requires_parent_applicability():
    source = _doc_with_file(project_id=1, product_id=10)
    user = User(id=1, login="tester", password_hash="x", role=UserRole.user)
    session = AsyncMock()
    session.execute = AsyncMock(return_value=MagicMock(all=MagicMock(return_value=[])))

    with pytest.raises(HTTPException) as exc:
        await verify_child_applicability(session, source, user)
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_verify_child_applicability_delegates_to_propagation():
    source = _doc_with_file(project_id=1, product_id=10)
    user = User(id=1, login="tester", password_hash="x", role=UserRole.user)
    session = AsyncMock()
    session.execute = AsyncMock(return_value=MagicMock(all=MagicMock(return_value=[(30,)])))

    with patch(
        "app.document_applicability.propagate_applicability_to_outgoing_links",
        new_callable=AsyncMock,
        return_value=[{"target_id": 20, "designation": "CHILD.001", "product_id": 30, "success": True}],
    ) as propagate:
        results = await verify_child_applicability(session, source, user)

    propagate.assert_awaited_once_with(session, source, user)
    assert results[0]["designation"] == "CHILD.001"


@pytest.mark.asyncio
async def test_add_document_applicability_many_calls_propagation(tmp_path):
    source_file = tmp_path / "source.pdf"
    source_file.write_bytes(b"pdf-content")
    doc = _doc_with_file(project_id=1, product_id=10)
    doc.file_path = str(source_file)
    user = User(id=1, login="tester", password_hash="x", role=UserRole.user)

    project = Project(id=2, name="Target", slug="target")
    product = Product(id=20, project_id=2, name="Target product", slug="target-product", project=project)

    session = AsyncMock()
    session.get = AsyncMock(return_value=product)
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()

    async def execute_side_effect(stmt):
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        result.all.return_value = []
        unique = MagicMock()
        unique.all.return_value = []
        scalars = MagicMock()
        scalars.unique.return_value = unique
        result.scalars.return_value = scalars
        return result

    session.execute = AsyncMock(side_effect=execute_side_effect)

    with patch("app.document_applicability.UPLOAD_DIR", str(tmp_path)), patch(
        "app.document_applicability.log_change_event", new_callable=AsyncMock
    ), patch("app.document_applicability.notify_document_edit", new_callable=AsyncMock), patch(
        "app.document_applicability.propagate_applicability_to_outgoing_links",
        new_callable=AsyncMock,
        return_value=[{"target_id": 99, "designation": "LINK.001", "product_id": 20, "success": True}],
    ) as propagate:
        created, propagated = await add_document_applicability_many(session, doc, [20], user)

    assert len(created) == 1
    propagate.assert_awaited_once()
    assert propagated[0]["designation"] == "LINK.001"
