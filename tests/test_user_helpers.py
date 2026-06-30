"""Tests for user name helpers."""

from app.user_helpers import is_digits_only, validate_person_fields


def test_is_digits_only():
    assert is_digits_only("123")
    assert is_digits_only(" 456 ")
    assert not is_digits_only("")
    assert not is_digits_only("  ")
    assert not is_digits_only("Ivan")
    assert not is_digits_only("123a")


def test_validate_person_fields_rejects_digits_only_names():
    assert validate_person_fields("123", "Ivan") == "name_digits"
    assert validate_person_fields("Ivan", "456") == "name_digits"
    assert validate_person_fields("Ivan", "Petrov", patronymic="789") == "name_digits"
    assert validate_person_fields("Ivan", "Petrov", position="123") == "position_digits"


def test_validate_person_fields_accepts_valid_values():
    assert validate_person_fields("Ivanov", "Ivan") is None
    assert validate_person_fields("Ivanov", "Ivan", patronymic="") is None
    assert validate_person_fields("Ivanov", "Ivan", position="Engineer") is None
