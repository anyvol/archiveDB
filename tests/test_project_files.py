"""Tests for project misc file registration and sync."""

import os
from io import BytesIO
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import UploadFile

from app.models import MISC_DOCS_FOLDER, Project, ProjectFile, User, UserRole
from app.project_files import (
    save_development_order_file,
    sync_project_misc_files,
    title_from_misc_filename,
)


def test_title_from_misc_filename_strips_uuid_prefix():
    assert title_from_misc_filename("a1b2c3d4_Приказ на включение в план.pdf") == (
        "Приказ на включение в план"
    )


def test_title_from_misc_filename_strips_trailing_uuid_suffix():
    assert title_from_misc_filename("Приказ на разработку_ab12cd34.pdf") == "Приказ на разработку"


@pytest.mark.asyncio
async def test_save_development_order_file_creates_project_file_record(tmp_path, monkeypatch):
    upload_dir = str(tmp_path)
    monkeypatch.setattr("app.config.UPLOAD_DIR", upload_dir)
    monkeypatch.setattr("app.project_helpers.UPLOAD_DIR", upload_dir)

    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()

    project = Project(id=1, name="Demo (ABC)", slug="demo-abc")
    user = User(id=7, login="tester", role=UserRole.user, password_hash="x")
    upload = UploadFile(filename="Приказ.pdf", file=BytesIO(b"pdf-content"))

    record = await save_development_order_file(session, project, upload, user)

    session.add.assert_called_once()
    added = session.add.call_args.args[0]
    assert isinstance(added, ProjectFile)
    assert added.project_id == 1
    assert added.uploaded_by == 7
    assert added.title == "Приказ"
    assert added.file_name.endswith(".pdf")
    assert MISC_DOCS_FOLDER in added.file_path
    assert record is added


@pytest.mark.asyncio
async def test_sync_project_misc_files_imports_orphan_files(tmp_path, monkeypatch):
    upload_dir = str(tmp_path)
    monkeypatch.setattr("app.config.UPLOAD_DIR", upload_dir)
    monkeypatch.setattr("app.project_helpers.UPLOAD_DIR", upload_dir)

    project = Project(id=2, name="Legacy", slug="legacy")
    misc_dir = os.path.join(tmp_path, project.slug, MISC_DOCS_FOLDER)
    os.makedirs(misc_dir, exist_ok=True)
    orphan_path = os.path.join(misc_dir, "deadbeef_Приказ на включение в план.pdf")
    with open(orphan_path, "wb") as handle:
        handle.write(b"content")

    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()

    known = MagicMock()
    known.all.return_value = []
    session.execute = AsyncMock(return_value=known)

    user = User(id=3, login="admin", role=UserRole.admin, password_hash="x")
    added = await sync_project_misc_files(session, project, user)

    assert added == 1
    session.add.assert_called_once()
    record = session.add.call_args.args[0]
    assert record.title == "Приказ на включение в план"
    assert record.file_name == "deadbeef_Приказ на включение в план.pdf"
    assert record.uploaded_by == 3


@pytest.mark.asyncio
async def test_sync_project_misc_files_skips_existing_records(tmp_path, monkeypatch):
    upload_dir = str(tmp_path)
    monkeypatch.setattr("app.config.UPLOAD_DIR", upload_dir)
    monkeypatch.setattr("app.project_helpers.UPLOAD_DIR", upload_dir)

    project = Project(id=2, name="Legacy", slug="legacy")
    misc_dir = os.path.join(tmp_path, project.slug, MISC_DOCS_FOLDER)
    os.makedirs(misc_dir, exist_ok=True)
    file_name = "deadbeef_Приказ.pdf"
    file_path = os.path.join(misc_dir, file_name)
    with open(file_path, "wb") as handle:
        handle.write(b"content")

    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()

    row = MagicMock()
    row.file_name = file_name
    row.file_path = file_path
    known = MagicMock()
    known.all.return_value = [row]
    session.execute = AsyncMock(return_value=known)

    user = User(id=3, login="admin", role=UserRole.admin, password_hash="x")
    added = await sync_project_misc_files(session, project, user)

    assert added == 0
    session.add.assert_not_called()
