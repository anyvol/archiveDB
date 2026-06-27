"""Helpers for building and parsing user full names."""


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
