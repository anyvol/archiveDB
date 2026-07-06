"""Helpers for building document designations and formatting execution suffixes."""
from __future__ import annotations

import re
from typing import Optional

from fastapi import HTTPException


EXECUTION_INPUT_PATTERN = re.compile(r"^\d{1,2}$")
EXECUTION_MAX_VALUE = 99


def parse_execution_input(raw: Optional[str]) -> Optional[str]:
    """
    Parse user execution input into a stored suffix (without leading dash).
    Examples: "1" -> "01", "15" -> "15", "" -> None.
    """
    value = (raw or "").strip()
    if not value:
        return None
    if not EXECUTION_INPUT_PATTERN.match(value):
        raise HTTPException(
            status_code=400,
            detail="Исполнение должно состоять из 1–2 цифр.",
        )
    number = int(value)
    if number < 1 or number > EXECUTION_MAX_VALUE:
        raise HTTPException(
            status_code=400,
            detail=f"Исполнение должно быть от 1 до {EXECUTION_MAX_VALUE}.",
        )
    return str(number).zfill(2)


def format_execution_suffix(execution: Optional[str]) -> str:
    """Return execution with leading dash for designation, e.g. '01' -> '-01'."""
    if not execution:
        return ""
    return f"-{execution}"


def build_designation(
    org_code: str,
    class_code: str,
    serial: int,
    *,
    execution: Optional[str] = None,
    doc_kind_code: Optional[str] = None,
) -> str:
    """Build full document designation from its components."""
    designation = f"{org_code}.{class_code}.{serial:03d}"
    designation += format_execution_suffix(execution)
    if doc_kind_code:
        designation += doc_kind_code
    return designation
