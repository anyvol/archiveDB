"""Tests for person name normalization."""

from app.name_helpers import normalize_person_name


def test_normalize_surname_only():
    assert normalize_person_name("Иванов") == "Иванов"


def test_normalize_full_name():
    assert normalize_person_name("Иванов Иван Иванович") == "Иванов Иван Иванович"


def test_normalize_trims_empty_parts():
    assert normalize_person_name("  Иванов   ") == "Иванов"


def test_normalize_initials():
    assert normalize_person_name("Иванов И.И.") == "Иванов И.И."
