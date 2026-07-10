"""Collect known person names and surnames from the database."""

from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import BaseDocument, User
from app.user_helpers import build_full_name, split_full_name

_PERSON_SPLIT = re.compile(r"[,;\n]+")


def normalize_person_name(value: str) -> str:
    """Return a single FIO string with empty parts trimmed (surname-only is allowed)."""
    value = (value or "").strip()
    if not value:
        return ""
    last_name, first_name, patronymic = split_full_name(value)
    if not last_name and not first_name and not patronymic:
        parts = [part for part in value.split() if part.strip()]
        if not parts:
            return ""
        if len(parts) == 1:
            return parts[0]
        if len(parts) == 2:
            return f"{parts[0]} {parts[1]}"
        return f"{parts[0]} {parts[1]} {' '.join(parts[2:])}"
    return build_full_name(last_name, first_name, patronymic)


def _add_person_value(names: set[str], raw: str | None) -> None:
    if not raw or not raw.strip():
        return
    for segment in _PERSON_SPLIT.split(raw):
        normalized = normalize_person_name(segment)
        if normalized:
            names.add(normalized)


async def fetch_known_person_names(session: AsyncSession) -> list[str]:
    """Return sorted unique normalized FIO values from users and documents."""
    names: set[str] = set()

    user_rows = await session.execute(select(User.full_name).where(User.full_name.isnot(None)))
    for (full_name,) in user_rows:
        _add_person_value(names, full_name)

    doc_rows = await session.execute(
        select(
            BaseDocument.developed_by,
            BaseDocument.created_by,
            BaseDocument.reviewed_by,
            BaseDocument.approved_by,
        )
    )
    for developed_by, created_by, reviewed_by, approved_by in doc_rows:
        _add_person_value(names, developed_by)
        _add_person_value(names, created_by)
        _add_person_value(names, reviewed_by)
        _add_person_value(names, approved_by)

    return sorted(names, key=lambda item: item.casefold())


def suggest_person_names(
    query: str,
    known_names: list[str],
    *,
    limit: int = 5,
    min_score: float = 55.0,
) -> list[dict]:
    """Fuzzy-match OCR surname/FIO against known names. Suggestions only — never auto-replace.

    Returns list of ``{name, score, reason}`` sorted by score desc.
    """
    needle = normalize_person_name(query)
    if not needle or not known_names:
        return []

    needle_cf = needle.casefold()
    needle_surname = needle_cf.split()[0]

    exact: list[dict] = []
    for name in known_names:
        name_cf = name.casefold()
        if name_cf == needle_cf:
            exact.append({"name": name, "score": 100.0, "reason": "exact"})
        elif name_cf.startswith(needle_surname + " ") or name_cf == needle_surname:
            exact.append({"name": name, "score": 95.0, "reason": "surname"})
    if exact:
        best: dict[str, dict] = {}
        for item in exact:
            prev = best.get(item["name"])
            if not prev or item["score"] > prev["score"]:
                best[item["name"]] = item
        return sorted(best.values(), key=lambda x: (-x["score"], x["name"].casefold()))[:limit]

    try:
        from rapidfuzz import fuzz, process
    except ImportError:
        return []

    scored = process.extract(
        needle,
        known_names,
        scorer=fuzz.WRatio,
        limit=limit * 3,
    )

    surname_map: dict[str, list[str]] = {}
    for name in known_names:
        sur = name.casefold().split()[0]
        surname_map.setdefault(sur, []).append(name)
    sur_hits = process.extract(
        needle_surname,
        list(surname_map.keys()),
        scorer=fuzz.WRatio,
        limit=limit,
    )

    merged: dict[str, dict] = {}
    for name, score, _ in scored:
        if score < min_score:
            continue
        merged[name] = {"name": name, "score": float(score), "reason": "fuzzy"}
    for sur, score, _ in sur_hits:
        if score < min_score:
            continue
        for name in surname_map.get(sur, []):
            prev = merged.get(name)
            entry = {"name": name, "score": float(score), "reason": "surname_fuzzy"}
            if not prev or entry["score"] > prev["score"]:
                merged[name] = entry

    return sorted(merged.values(), key=lambda x: (-x["score"], x["name"].casefold()))[:limit]


async def fetch_known_org_codes(session: AsyncSession) -> list[str]:
    """Return sorted unique organization codes from organizations and documents."""
    from app.models import DesignDocument, Organization, TechDocument

    codes: set[str] = set()
    org_rows = await session.execute(
        select(Organization.code, Organization.num_code, Organization.num_code_okpo)
    )
    for code, num_code, num_okpo in org_rows:
        if code:
            codes.add(str(code).strip())
        if num_code is not None:
            codes.add(f"{int(num_code):08d}" if int(num_code) < 10_000_000 else str(int(num_code)))
            codes.add(str(int(num_code)))
        if num_okpo is not None:
            codes.add(f"{int(num_okpo):08d}")
            codes.add(str(int(num_okpo)))

    for model in (DesignDocument, TechDocument):
        rows = await session.execute(select(model.org_code_str).where(model.org_code_str.isnot(None)))
        for (org_code,) in rows:
            if org_code and str(org_code).strip():
                codes.add(str(org_code).strip())

    return sorted(codes, key=lambda item: item.casefold())


def suggest_org_codes(
    query: str,
    known_codes: list[str],
    *,
    limit: int = 5,
    min_score: float = 60.0,
) -> list[dict]:
    """Fuzzy-match OCR org code against known codes. Suggestions only."""
    needle = (query or "").strip().replace(" ", "").upper()
    if not needle or not known_codes:
        return []

    exact = [c for c in known_codes if c.casefold() == needle.casefold()]
    if exact:
        return [{"name": c, "score": 100.0, "reason": "exact"} for c in exact[:limit]]

    prefix = [c for c in known_codes if c.casefold().startswith(needle.casefold())]
    if prefix:
        return [{"name": c, "score": 90.0, "reason": "prefix"} for c in prefix[:limit]]

    try:
        from rapidfuzz import fuzz, process
    except ImportError:
        return []

    scored = process.extract(needle, known_codes, scorer=fuzz.WRatio, limit=limit * 2)
    out: list[dict] = []
    for code, score, _ in scored:
        if score < min_score:
            continue
        out.append({"name": code, "score": float(score), "reason": "fuzzy"})
    return out[:limit]

