"""Парсинг переменных окружения для конфигурации."""

from __future__ import annotations

import os


def env_str(name: str, default: str) -> str:
    value = os.getenv(name)
    return value.strip() if isinstance(value, str) else default


def env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value.strip())
    except (TypeError, ValueError):
        return default


def env_int_list(name: str, default: list[int] | None = None) -> list[int]:
    """Список целых через запятую и/или с новой строки; пустое значение — default."""
    value = os.getenv(name)
    if value is None or not value.strip():
        return list(default) if default is not None else []
    items: list[int] = []
    for part in value.replace("\n", ",").split(","):
        token = part.strip()
        if not token:
            continue
        try:
            items.append(int(token))
        except ValueError:
            continue
    return items if items else (list(default) if default is not None else [])


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    return default
