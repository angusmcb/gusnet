from __future__ import annotations

import gettext
from pathlib import Path

DOMAIN = "gusnet"
LOCALE_DIR = Path(__file__).resolve().parent / "resources" / "i18n" / "locales"

_translation: gettext.NullTranslations = gettext.NullTranslations()


def _normalize_languages(lang_code: str) -> list[str]:
    primary = lang_code.split(".")[0].replace("-", "_")
    short = primary.split("_")[0]
    if primary == short:
        return [primary]
    return [primary, short]


def set_locale(lang_code: str | None) -> None:
    """Load gettext catalog for the given locale code."""
    global _translation

    normalized = (lang_code or "en").lower().strip()
    _translation = gettext.translation(
        DOMAIN,
        localedir=str(LOCALE_DIR),
        languages=_normalize_languages(normalized),
        fallback=True,
    )


def tr(text: str) -> str:
    """Get translated text from gettext catalogs."""

    return _translation.gettext(text)


def trn(singular, plural, count, **kwargs):
    return _translation.ngettext(singular, plural, count).format(count=count, **kwargs)


set_locale("en")
