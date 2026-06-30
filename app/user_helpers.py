"""Helpers for building and parsing user full names."""


def is_digits_only(value: str) -> bool:
    stripped = value.strip()
    return bool(stripped) and stripped.isdigit()


def validate_person_fields(
    last_name: str,
    first_name: str,
    patronymic: str = "",
    position: str = "",
) -> str | None:
    """Return an error code when a name or position field is digits-only."""
    if is_digits_only(last_name) or is_digits_only(first_name):
        return "name_digits"
    if patronymic.strip() and is_digits_only(patronymic):
        return "name_digits"
    if position.strip() and is_digits_only(position):
        return "position_digits"
    return None


def build_full_name(last_name: str, first_name: str, patronymic: str = "") -> str:
    parts = [last_name.strip(), first_name.strip()]
    patronymic = patronymic.strip()
    if patronymic:
        parts.append(patronymic)
    return " ".join(part for part in parts if part)


def split_full_name(full_name: str | None) -> tuple[str, str, str]:
    if not full_name:
        return "", "", ""
    parts = full_name.split()
    if len(parts) == 0:
        return "", "", ""
    if len(parts) == 1:
        return parts[0], "", ""
    if len(parts) == 2:
        return parts[0], parts[1], ""
    return parts[0], parts[1], " ".join(parts[2:])
