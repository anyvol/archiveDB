import pytest
from fastapi import HTTPException

from app.designation_helpers import (
    build_designation,
    format_execution_suffix,
    parse_execution_input,
)


def test_parse_execution_input_empty():
    assert parse_execution_input("") is None
    assert parse_execution_input(None) is None
    assert parse_execution_input("   ") is None


def test_parse_execution_input_formats():
    assert parse_execution_input("1") == "01"
    assert parse_execution_input("01") == "01"
    assert parse_execution_input("15") == "15"
    assert parse_execution_input("150") == "150"


def test_parse_execution_input_invalid():
    with pytest.raises(HTTPException) as exc:
        parse_execution_input("abc")
    assert exc.value.status_code == 400

    with pytest.raises(HTTPException):
        parse_execution_input("0")


def test_format_execution_suffix():
    assert format_execution_suffix(None) == ""
    assert format_execution_suffix("01") == "-01"
    assert format_execution_suffix("15") == "-15"


def test_build_designation_with_execution_and_kind():
    assert build_designation("ФЕТР", "000000", 1) == "ФЕТР.000000.001"
    assert build_designation("ФЕТР", "000000", 1, execution="01") == "ФЕТР.000000.001-01"
    assert build_designation("ФЕТР", "000000", 1, doc_kind_code="СБ") == "ФЕТР.000000.001СБ"
    assert (
        build_designation("ФЕТР", "000000", 1, execution="02", doc_kind_code="ГЧ")
        == "ФЕТР.000000.001-02ГЧ"
    )


def test_build_designation_different_kinds_same_serial():
    sb = build_designation("ФЕТР", "000000", 1, doc_kind_code="СБ")
    gch = build_designation("ФЕТР", "000000", 1, doc_kind_code="ГЧ")
    assert sb != gch


def test_build_designation_different_executions_same_serial():
    first = build_designation("ФЕТР", "000000", 1, execution="01")
    second = build_designation("ФЕТР", "000000", 1, execution="02")
    assert first != second
