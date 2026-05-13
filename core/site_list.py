"""Список узлов для проверки и разбор хост:порт из строки."""

from __future__ import annotations

from pathlib import Path

from config.settings import SITE_PORT, SITES_FILE, SITES_TO_CHECK
from core.logger import logger


def normalize_host_port(site: str, default_port: int) -> tuple[str, int]:
    s = site.strip()
    if "://" in s:
        s = s.split("://", 1)[1]
    s = s.split("/", 1)[0]
    if s.startswith("["):
        br = s.find("]")
        if br != -1 and len(s) > br + 1 and s[br + 1] == ":":
            return s[1:br], int(s[br + 2 :])
        return s[1:br] if br != -1 else s, default_port
    if ":" in s:
        host, _, port_s = s.rpartition(":")
        if port_s.isdigit():
            return host, int(port_s)
    return s, default_port


def _split_site_tokens(raw: str) -> list[str]:
    tokens: list[str] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        for part in line.split(","):
            p = part.strip()
            if p:
                tokens.append(p)
    return tokens


def load_site_entries() -> list[tuple[str, int]]:
    raw = ""
    sf = SITES_FILE.strip()
    if sf:
        path = Path(sf)
        if path.is_file():
            raw = path.read_text(encoding="utf-8")
        else:
            logger.warning("SITES_FILE не найден ({}), читается SITES_TO_CHECK из .env", path)
    if not raw.strip():
        raw = SITES_TO_CHECK.strip()
    tokens = _split_site_tokens(raw) if raw.strip() else []
    if not tokens:
        logger.error(
            "Список узлов для проверки пуст. Заполните SITES_TO_CHECK или SITES_FILE в .env (см. .env.example)."
        )
        raise ValueError(
            "Не заданы узлы для проверки: укажите SITES_TO_CHECK или файл SITES_FILE в настройках (.env)."
        )
    return [normalize_host_port(t, SITE_PORT) for t in tokens]
