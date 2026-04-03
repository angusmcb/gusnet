from __future__ import annotations

import gettext
import re
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


def _qt_style_plural_message(text: str) -> tuple[str, str]:
    """Convert Qt-style '(s)' placeholders into singular/plural strings."""

    singular = text.replace("(s)", "")
    plural = re.sub(r"\(s\)", "s", text)
    return singular, plural


def tr(
    text: str,
    disambiguation: str = "",  # noqa: ARG001
    n=-1,
    context: str = "@default",  # noqa: ARG001
) -> str:
    """Get translated text from gettext catalogs.

    :param text: String for translation.
    :param context: Context of the translation.
    :param n: Optional quantity for pluralized strings.

    :returns: Translated version of message.
    """
    if n == -1:
        return _translation.gettext(text)

    singular, plural = _qt_style_plural_message(text)
    translated = _translation.ngettext(singular, plural, n)
    return translated.replace("%n", str(n))


set_locale("en")
