"""Tests for project helpers."""

import pytest

from app.project_helpers import slugify_project_name, format_project_name


@pytest.mark.parametrize(
    "name,expected",
    [
        ("Танк-300", "Танк-300"),
        ("  My Project  ", "My-Project"),
        ('Bad/name:test', "Bad_name_test"),
        ("", "project"),
        ("..." , "project"),
    ],
)
def test_slugify_project_name(name, expected):
    assert slugify_project_name(name) == expected


def test_format_project_name():
    assert format_project_name("Танк", "Т-300") == "Танк (Т-300)"
