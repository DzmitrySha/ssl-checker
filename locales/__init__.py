"""i18n engine for ssl-checker."""

from __future__ import annotations

from config.settings import LANGUAGE
from locales import en, ru

_AVAILABLE_LANGS = {"en": en.EN, "ru": ru.RU}
_DEFAULT_LANG = "ru"


class TranslationEngine:
    __slots__ = ("_lang", "_strings")

    def __init__(self, lang: str | None = None) -> None:
        self._lang = lang or LANGUAGE or _DEFAULT_LANG
        self._strings = _AVAILABLE_LANGS.get(self._lang, _AVAILABLE_LANGS[_DEFAULT_LANG])

    def __call__(self, key: str, **kwargs) -> str:
        if key not in self._strings:
            return key
        template = self._strings[key]
        try:
            return template.format(**kwargs)
        except (IndexError, KeyError):
            return template


_translation_engine: TranslationEngine | None = None


def init_translation(lang: str | None = None) -> None:
    global _translation_engine
    _translation_engine = TranslationEngine(lang)


def _(key: str, **kwargs) -> str:
    if _translation_engine is None:
        init_translation()
    assert _translation_engine is not None
    return _translation_engine(key, **kwargs)


def get_current_lang() -> str:
    if _translation_engine is None:
        init_translation()
    assert _translation_engine is not None
    return _translation_engine._lang


def set_lang(lang: str) -> None:
    global _translation_engine
    _translation_engine = TranslationEngine(lang)


def get_available_langs() -> list[str]:
    return list(_AVAILABLE_LANGS.keys())