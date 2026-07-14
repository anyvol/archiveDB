"""Archive notifications (ИИ), orders (приказы), and technical specs (ТУ) registration and queries."""

from __future__ import annotations

import os
import re
from datetime import datetime

from fastapi import HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import joinedload

from app.config import UPLOAD_DIR
from app.document_helpers import (
    _read_upload_contents,
    _sanitize_storage_name,
    validate_upload_file,
)
from app.models import (
    ArchiveNotification,
    ArchiveOrder,
    ArchiveTechnicalSpec,
    BaseDocument,
    ChangeNotification,
    II_FOLDER,
    ORDERS_FOLDER,
    Product,
    Project,
    TU_ARCHIVE_FOLDER,
    User,
)

TU_NUMBER_PATTERN = re.compile(
    r"^(?P<okpd2>\d{2}\.\d{2}\.\d{2})-(?P<product_index>\d{1,3})-(?P<okpo>\d{8})-(?P<year>\d{4})$"
)


def _ii_storage_dir(project_slug: str, product_slug: str) -> str:
    path = os.path.join(UPLOAD_DIR, project_slug, product_slug, II_FOLDER)
    os.makedirs(path, exist_ok=True)
    return path


def _orders_storage_dir() -> str:
    path = os.path.join(UPLOAD_DIR, ORDERS_FOLDER)
    os.makedirs(path, exist_ok=True)
    return path


def _tu_storage_dir() -> str:
    path = os.path.join(UPLOAD_DIR, TU_ARCHIVE_FOLDER)
    os.makedirs(path, exist_ok=True)
    return path


def build_tu_number(okpd2: str, product_index: str, okpo: str, year: int | str) -> str:
    okpd2 = okpd2.strip()
    product_index = product_index.strip()
    okpo = okpo.strip()
    year_str = str(year).strip()
    if not TU_NUMBER_PATTERN.match(f"{okpd2}-{product_index}-{okpo}-{year_str}"):
        raise HTTPException(
            status_code=400,
            detail=(
                "Номер ТУ должен соответствовать формату "
                "ОКПД 2-порядковый номер ТУ-ОКПО организации-год "
                "(например, 26.20.13-002-95979699-2024)."
            ),
        )
    normalized_index = str(int(product_index)).zfill(3)
    return f"{okpd2}-{normalized_index}-{okpo}-{year_str}"


def parse_tu_number(number: str) -> dict[str, str | int]:
    match = TU_NUMBER_PATTERN.match(number.strip())
    if not match:
        raise HTTPException(status_code=400, detail="Некорректный номер ТУ.")
    return {
        "okpd2": match.group("okpd2"),
        "product_index": str(int(match.group("product_index"))).zfill(3),
        "okpo": match.group("okpo"),
        "year": int(match.group("year")),
    }


async def _ensure_unique_notification_number(session: AsyncSession, number: str) -> None:
    result = await session.execute(
        select(ArchiveNotification.id).where(ArchiveNotification.number == number.strip())
    )
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Номер извещения уже зарегистрирован в архиве.")


async def _ensure_unique_order_number(session: AsyncSession, number: str) -> None:
    result = await session.execute(
        select(ArchiveOrder.id).where(ArchiveOrder.number == number.strip())
    )
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Номер приказа уже зарегистрирован в архиве.")


async def _ensure_unique_tu_number(session: AsyncSession, number: str) -> None:
    result = await session.execute(
        select(ArchiveTechnicalSpec.id).where(ArchiveTechnicalSpec.number == number.strip())
    )
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Номер ТУ уже зарегистрирован в архиве.")


async def create_archive_notification(
    session: AsyncSession,
    user: User,
    *,
    number: str,
    change_number: str,
    change_date: datetime,
    project_id: int,
    product_id: int,
    ii_file: UploadFile,
    developer_signed: bool,
    reviewer_signed: bool,
    approver_signed: bool,
) -> ArchiveNotification:
    if not number.strip():
        raise HTTPException(status_code=400, detail="Укажите номер извещения об изменении.")
    if not change_number.strip():
        raise HTTPException(status_code=400, detail="Укажите номер изменения.")
    if not developer_signed or not reviewer_signed or not approver_signed:
        raise HTTPException(status_code=400, detail="Отметьте все подписи на извещении.")

    await _ensure_unique_notification_number(session, number)
    validate_upload_file(ii_file)

    product = await session.get(
        Product,
        product_id,
        options=[joinedload(Product.project)],
    )
    if not product or not product.project:
        raise HTTPException(status_code=404, detail="Изделие не найдено.")
    if product.project_id != project_id:
        raise HTTPException(status_code=400, detail="Изделие не относится к выбранному проекту.")

    contents, original = await _read_upload_contents(ii_file)
    stored_name = _sanitize_storage_name(original)
    storage_dir = _ii_storage_dir(product.project.slug, product.slug)
    file_path = os.path.join(storage_dir, stored_name)
    if os.path.exists(file_path):
        base, ext = os.path.splitext(stored_name)
        counter = 1
        while os.path.exists(file_path):
            stored_name = _sanitize_storage_name(f"{base}_{counter}{ext}")
            file_path = os.path.join(storage_dir, stored_name)
            counter += 1
    with open(file_path, "wb") as handle:
        handle.write(contents)

    record = ArchiveNotification(
        number=number.strip(),
        change_number=change_number.strip(),
        change_date=change_date,
        project_id=project_id,
        product_id=product_id,
        file_name=stored_name,
        file_path=file_path,
        developer_signed=developer_signed,
        reviewer_signed=reviewer_signed,
        approver_signed=approver_signed,
        created_by_user_id=user.id,
    )
    session.add(record)
    await session.flush()
    return record


async def create_archive_order(
    session: AsyncSession,
    user: User,
    *,
    number: str,
    name: str,
    order_date: datetime,
    order_file: UploadFile,
) -> ArchiveOrder:
    if not number.strip():
        raise HTTPException(status_code=400, detail="Укажите номер приказа.")
    if not name.strip():
        raise HTTPException(status_code=400, detail="Укажите название приказа.")

    await _ensure_unique_order_number(session, number)
    validate_upload_file(order_file)

    contents, original = await _read_upload_contents(order_file)
    stored_name = _sanitize_storage_name(original)
    storage_dir = _orders_storage_dir()
    file_path = os.path.join(storage_dir, stored_name)
    if os.path.exists(file_path):
        base, ext = os.path.splitext(stored_name)
        counter = 1
        while os.path.exists(file_path):
            stored_name = _sanitize_storage_name(f"{base}_{counter}{ext}")
            file_path = os.path.join(storage_dir, stored_name)
            counter += 1
    with open(file_path, "wb") as handle:
        handle.write(contents)

    record = ArchiveOrder(
        number=number.strip(),
        name=name.strip(),
        order_date=order_date,
        file_name=stored_name,
        file_path=file_path,
        created_by_user_id=user.id,
    )
    session.add(record)
    await session.flush()
    return record


async def create_archive_technical_spec(
    session: AsyncSession,
    user: User,
    *,
    okpd2: str,
    product_index: str,
    okpo: str,
    year: int,
    name: str,
    tu_file: UploadFile,
) -> ArchiveTechnicalSpec:
    if not name.strip():
        raise HTTPException(status_code=400, detail="Укажите наименование изделия.")
    number = build_tu_number(okpd2, product_index, okpo, year)
    await _ensure_unique_tu_number(session, number)
    validate_upload_file(tu_file)

    parsed = parse_tu_number(number)
    contents, original = await _read_upload_contents(tu_file)
    stored_name = _sanitize_storage_name(original)
    storage_dir = _tu_storage_dir()
    file_path = os.path.join(storage_dir, stored_name)
    if os.path.exists(file_path):
        base, ext = os.path.splitext(stored_name)
        counter = 1
        while os.path.exists(file_path):
            stored_name = _sanitize_storage_name(f"{base}_{counter}{ext}")
            file_path = os.path.join(storage_dir, stored_name)
            counter += 1
    with open(file_path, "wb") as handle:
        handle.write(contents)

    record = ArchiveTechnicalSpec(
        number=number,
        name=name.strip(),
        okpd2=str(parsed["okpd2"]),
        product_index=str(parsed["product_index"]),
        okpo=str(parsed["okpo"]),
        year=int(parsed["year"]),
        file_name=stored_name,
        file_path=file_path,
        created_by_user_id=user.id,
    )
    session.add(record)
    await session.flush()
    return record


async def fetch_archive_notifications(
    session: AsyncSession,
    *,
    limit: int = 20,
    offset: int = 0,
    number: str | None = None,
    change_number: str | None = None,
    project_id: str | None = None,
    product_id: str | None = None,
    sort: str = "created_at",
    order: str = "desc",
) -> tuple[list[ArchiveNotification], int]:
    query = select(ArchiveNotification).options(
        joinedload(ArchiveNotification.project),
        joinedload(ArchiveNotification.product),
        joinedload(ArchiveNotification.created_by),
    )
    if number:
        query = query.where(ArchiveNotification.number.ilike(f"%{number}%"))
    if change_number:
        query = query.where(ArchiveNotification.change_number.ilike(f"%{change_number}%"))
    if project_id:
        try:
            query = query.where(ArchiveNotification.project_id == int(project_id))
        except ValueError:
            pass
    if product_id:
        try:
            query = query.where(ArchiveNotification.product_id == int(product_id))
        except ValueError:
            pass

    count_result = await session.execute(select(ArchiveNotification.id))
    total = len(count_result.all())

    sort_columns = {
        "number": ArchiveNotification.number,
        "change_number": ArchiveNotification.change_number,
        "change_date": ArchiveNotification.change_date,
        "created_at": ArchiveNotification.created_at,
        "project": ArchiveNotification.project_id,
        "product": ArchiveNotification.product_id,
    }
    sort_col = sort_columns.get(sort, ArchiveNotification.created_at)
    if order == "asc":
        query = query.order_by(sort_col.asc())
    else:
        query = query.order_by(sort_col.desc())

    result = await session.execute(query.offset(offset).limit(limit))
    return list(result.scalars().unique().all()), total


async def fetch_archive_orders(
    session: AsyncSession,
    *,
    limit: int = 20,
    offset: int = 0,
    number: str | None = None,
    name: str | None = None,
    project_id: str | None = None,
    product_id: str | None = None,
    sort: str = "created_at",
    order: str = "desc",
) -> tuple[list[ArchiveOrder], int]:
    query = select(ArchiveOrder).options(
        joinedload(ArchiveOrder.created_by),
        joinedload(ArchiveOrder.project),
        joinedload(ArchiveOrder.products),
    )
    if number:
        query = query.where(ArchiveOrder.number.ilike(f"%{number}%"))
    if name:
        query = query.where(ArchiveOrder.name.ilike(f"%{name}%"))
    if project_id:
        try:
            query = query.where(ArchiveOrder.project_id == int(project_id))
        except ValueError:
            pass
    if product_id:
        try:
            pid = int(product_id)
            query = query.where(ArchiveOrder.products.any(Product.id == pid))
        except ValueError:
            pass

    count_result = await session.execute(select(ArchiveOrder.id))
    total = len(count_result.all())

    sort_columns = {
        "number": ArchiveOrder.number,
        "name": ArchiveOrder.name,
        "order_date": ArchiveOrder.order_date,
        "created_at": ArchiveOrder.created_at,
        "project": ArchiveOrder.project_id,
    }
    sort_col = sort_columns.get(sort, ArchiveOrder.created_at)
    if order == "asc":
        query = query.order_by(sort_col.asc())
    else:
        query = query.order_by(sort_col.desc())

    result = await session.execute(query.offset(offset).limit(limit))
    return list(result.scalars().unique().all()), total


async def fetch_archive_technical_specs(
    session: AsyncSession,
    *,
    limit: int = 20,
    offset: int = 0,
    number: str | None = None,
    name: str | None = None,
    okpo: str | None = None,
    sort: str = "created_at",
    order: str = "desc",
) -> tuple[list[ArchiveTechnicalSpec], int]:
    query = select(ArchiveTechnicalSpec).options(joinedload(ArchiveTechnicalSpec.created_by))
    if number:
        query = query.where(ArchiveTechnicalSpec.number.ilike(f"%{number}%"))
    if name:
        query = query.where(ArchiveTechnicalSpec.name.ilike(f"%{name}%"))
    if okpo:
        query = query.where(ArchiveTechnicalSpec.okpo.ilike(f"%{okpo}%"))

    count_result = await session.execute(select(ArchiveTechnicalSpec.id))
    total = len(count_result.all())

    sort_columns = {
        "number": ArchiveTechnicalSpec.number,
        "name": ArchiveTechnicalSpec.name,
        "year": ArchiveTechnicalSpec.year,
        "okpo": ArchiveTechnicalSpec.okpo,
        "created_at": ArchiveTechnicalSpec.created_at,
    }
    sort_col = sort_columns.get(sort, ArchiveTechnicalSpec.created_at)
    if order == "asc":
        query = query.order_by(sort_col.asc())
    else:
        query = query.order_by(sort_col.desc())

    result = await session.execute(query.offset(offset).limit(limit))
    return list(result.scalars().unique().all()), total


async def get_archive_notification(session: AsyncSession, record_id: int) -> ArchiveNotification | None:
    result = await session.execute(
        select(ArchiveNotification)
        .options(
            joinedload(ArchiveNotification.project),
            joinedload(ArchiveNotification.product),
            joinedload(ArchiveNotification.created_by),
        )
        .where(ArchiveNotification.id == record_id)
    )
    return result.scalar_one_or_none()


async def get_archive_order(session: AsyncSession, record_id: int) -> ArchiveOrder | None:
    result = await session.execute(
        select(ArchiveOrder)
        .options(
            joinedload(ArchiveOrder.created_by),
            joinedload(ArchiveOrder.project),
            joinedload(ArchiveOrder.products),
        )
        .where(ArchiveOrder.id == record_id)
    )
    return result.scalar_one_or_none()


async def get_archive_technical_spec(session: AsyncSession, record_id: int) -> ArchiveTechnicalSpec | None:
    result = await session.execute(
        select(ArchiveTechnicalSpec)
        .options(joinedload(ArchiveTechnicalSpec.created_by))
        .where(ArchiveTechnicalSpec.id == record_id)
    )
    return result.scalar_one_or_none()


async def list_available_archive_notifications(session: AsyncSession) -> list[ArchiveNotification]:
    result = await session.execute(
        select(ArchiveNotification)
        .options(
            joinedload(ArchiveNotification.project),
            joinedload(ArchiveNotification.product),
        )
        .order_by(ArchiveNotification.number.asc())
    )
    return list(result.scalars().unique().all())


async def list_available_archive_orders(session: AsyncSession) -> list[ArchiveOrder]:
    result = await session.execute(
        select(ArchiveOrder).order_by(ArchiveOrder.number.asc())
    )
    return list(result.scalars().all())


async def list_available_archive_technical_specs(session: AsyncSession) -> list[ArchiveTechnicalSpec]:
    result = await session.execute(
        select(ArchiveTechnicalSpec).order_by(ArchiveTechnicalSpec.number.asc())
    )
    return list(result.scalars().all())


async def update_archive_order_metadata(
    session: AsyncSession,
    record: ArchiveOrder,
    *,
    project_id: int | None,
    product_ids: list[int],
) -> None:
    if project_id is not None:
        project = await session.get(Project, project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Проект не найден.")
        record.project_id = project_id
    else:
        record.project_id = None
        record.products = []
        await session.flush()
        return

    if not product_ids:
        record.products = []
        await session.flush()
        return

    products: list[Product] = []
    for product_id in product_ids:
        product = await session.get(Product, product_id)
        if not product:
            raise HTTPException(status_code=404, detail="Изделие не найдено.")
        if product.project_id != project_id:
            raise HTTPException(status_code=400, detail="Изделие не относится к выбранному проекту.")
        products.append(product)
    record.products = products
    await session.flush()


async def get_notification_usage_places(
    session: AsyncSession,
    archive_notification_id: int,
) -> list[dict]:
    """Projects/products where the archive notification was used for formal changes."""
    result = await session.execute(
        select(ChangeNotification)
        .options(
            joinedload(ChangeNotification.document).joinedload(BaseDocument.project),
            joinedload(ChangeNotification.document).joinedload(BaseDocument.product),
        )
        .where(ChangeNotification.archive_notification_id == archive_notification_id)
    )
    usages = result.scalars().unique().all()
    places: list[dict] = []
    seen: set[tuple[int | None, int | None]] = set()
    for usage in usages:
        doc = usage.document
        if not doc:
            continue
        key = (doc.project_id, doc.product_id)
        if key in seen:
            continue
        seen.add(key)
        places.append(
            {
                "project_id": doc.project_id,
                "project_name": doc.project.name if doc.project else "—",
                "product_id": doc.product_id,
                "product_name": doc.product.name if doc.product else "—",
                "document_id": doc.id,
            }
        )
    return places


async def delete_archive_notification(
    session: AsyncSession,
    record: ArchiveNotification,
) -> None:
    used = await session.execute(
        select(ChangeNotification.id).where(
            ChangeNotification.archive_notification_id == record.id
        ).limit(1)
    )
    if used.scalar_one_or_none():
        raise HTTPException(
            status_code=400,
            detail="Нельзя удалить извещение: оно использовано для изменения документов.",
        )
    if record.file_path and os.path.exists(record.file_path):
        os.remove(record.file_path)
    await session.delete(record)


async def delete_archive_order(session: AsyncSession, record: ArchiveOrder) -> None:
    project_using = await session.execute(
        select(Project.id).where(Project.establishing_order_id == record.id).limit(1)
    )
    if project_using.scalar_one_or_none():
        raise HTTPException(
            status_code=400,
            detail="Нельзя удалить приказ: он назначен устанавливающим документом проекта.",
        )
    if record.file_path and os.path.exists(record.file_path):
        os.remove(record.file_path)
    await session.delete(record)


async def delete_archive_technical_spec(session: AsyncSession, record: ArchiveTechnicalSpec) -> None:
    project_using = await session.execute(
        select(Project.id).where(Project.establishing_tu_id == record.id).limit(1)
    )
    if project_using.scalar_one_or_none():
        raise HTTPException(
            status_code=400,
            detail="Нельзя удалить ТУ: оно назначено устанавливающим документом проекта.",
        )
    if record.file_path and os.path.exists(record.file_path):
        os.remove(record.file_path)
    await session.delete(record)
