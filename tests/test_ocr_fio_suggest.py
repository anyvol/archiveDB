"""Tests for fuzzy FIO suggestions (OCR phase 1B)."""

from app.name_helpers import suggest_person_names


def test_suggest_exact_and_surname():
    known = ["Волков Андрей Николаевич", "Иванов Иван Иванович", "Боков Пётр"]
    hits = suggest_person_names("Волков", known)
    assert hits
    assert hits[0]["name"].startswith("Волков")
    assert hits[0]["score"] >= 95


def test_suggest_fuzzy_bolkov_to_volkov():
    known = ["Волков Андрей Николаевич", "Иванов Иван"]
    hits = suggest_person_names("Болков", known, min_score=50)
    assert any("Волков" in h["name"] for h in hits)


def test_suggest_empty_query():
    assert suggest_person_names("", ["Волков"]) == []
