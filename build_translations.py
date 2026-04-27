from __future__ import annotations

import argparse
import subprocess
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DOMAIN = "messages"
BABEL_CONFIG = ROOT / "babel.cfg"
SOURCE_DIR = ROOT / "gusnet"
I18N_ROOT = SOURCE_DIR / "resources" / "i18n"
LOCALES_DIR = I18N_ROOT
TEMPLATE_PATH = I18N_ROOT / "messages.pot"
DEFAULT_LOCALES = ["ar", "de", "es", "fr", "it", "nl", "pt"]
BABEL_CMD = "pybabel"
TRANSLATION_REGRESSION_ERROR = "translation regression check failed"


@dataclass
class CatalogStats:
    translated: int = 0
    fuzzy: int = 0
    obsolete: int = 0


def run(cmd: list[str]) -> None:
    print("  ->", " ".join(cmd))
    subprocess.run(cmd, check=True)  # noqa: S603


def extract() -> None:
    """Extract translatable strings to the POT template."""
    LOCALES_DIR.mkdir(parents=True, exist_ok=True)
    run(
        [
            BABEL_CMD,
            "extract",
            "--add-location=file",
            "--omit-header",
            "--mapping-file",
            str(BABEL_CONFIG),
            "--output-file",
            str(TEMPLATE_PATH),
            ".",
        ]
    )


def init() -> None:
    """Initialize missing locale catalogs from the POT template."""
    for locale in DEFAULT_LOCALES:
        po_path = LOCALES_DIR / locale / "LC_MESSAGES" / f"{DOMAIN}.po"
        if po_path.exists():
            print(f"  -> Skipping init of existing locale: {locale}")
            continue
        print(f"  -> Initializing locale: {locale}")
        run(
            [
                BABEL_CMD,
                "init",
                "--input-file",
                str(TEMPLATE_PATH),
                "--domain",
                DOMAIN,
                "--locale",
                locale,
                "--output-dir",
                str(LOCALES_DIR),
            ]
        )


def update(*, previous: bool = True, ignore_obsolete: bool = False) -> None:
    """Update existing locale catalogs from the POT template."""

    options: list[str] = []
    if previous:
        options.append("--previous")
    if ignore_obsolete:
        options.append("--ignore-obsolete")

    run(
        [
            BABEL_CMD,
            "update",
            "--input-file",
            str(TEMPLATE_PATH),
            "--domain",
            DOMAIN,
            "--output-dir",
            str(LOCALES_DIR),
            *options,
        ]
    )


def _catalog_path(locale: str) -> Path:
    return LOCALES_DIR / locale / "LC_MESSAGES" / f"{DOMAIN}.po"


def _extract_quoted(line: str) -> str:
    first = line.find('"')
    last = line.rfind('"')
    if first == -1 or last <= first:
        return ""
    return line[first + 1 : last]


def _read_catalog_stats(po_path: Path) -> CatalogStats:
    if not po_path.exists():
        return CatalogStats()

    stats = CatalogStats()
    lines = po_path.read_text(encoding="utf-8").splitlines()

    in_entry = False
    pending_fuzzy = False
    entry_obsolete = False
    entry_fuzzy = False
    collecting_msgstr = False
    msgstr_buffers: list[str] = []
    current_msgstr = ""

    def finish_msgstr() -> None:
        nonlocal collecting_msgstr, current_msgstr
        if collecting_msgstr:
            msgstr_buffers.append(current_msgstr)
            current_msgstr = ""
            collecting_msgstr = False

    def finish_entry() -> None:
        nonlocal in_entry, entry_obsolete, entry_fuzzy, msgstr_buffers
        finish_msgstr()
        if not in_entry:
            return

        if entry_obsolete:
            stats.obsolete += 1
        else:
            if entry_fuzzy:
                stats.fuzzy += 1
            if any(value.strip() for value in msgstr_buffers):
                stats.translated += 1

        in_entry = False
        entry_obsolete = False
        entry_fuzzy = False
        msgstr_buffers = []

    for raw_line in [*lines, ""]:
        stripped = raw_line.strip()
        is_obsolete_line = stripped.startswith("#~")
        content = stripped[2:].lstrip() if is_obsolete_line else stripped

        if stripped.startswith("#,") and "fuzzy" in stripped and not in_entry:
            pending_fuzzy = True
            continue

        if content.startswith("msgid "):
            finish_entry()
            in_entry = True
            entry_obsolete = is_obsolete_line
            entry_fuzzy = pending_fuzzy and not entry_obsolete
            pending_fuzzy = False
            msgstr_buffers = []
            continue

        if not in_entry:
            if stripped == "":
                pending_fuzzy = False
            continue

        if content.startswith("msgstr"):
            finish_msgstr()
            current_msgstr = _extract_quoted(content)
            collecting_msgstr = True
            continue

        if content.startswith('"'):
            if collecting_msgstr:
                current_msgstr += _extract_quoted(content)
            continue

        if stripped == "":
            finish_entry()
            pending_fuzzy = False
            continue

        finish_msgstr()

    return stats


def _snapshot_stats(locales: list[str]) -> dict[str, CatalogStats]:
    return {locale: _read_catalog_stats(_catalog_path(locale)) for locale in locales}


def safe_update(*, allow_translation_drop: bool = False) -> None:
    locales = DEFAULT_LOCALES
    before = _snapshot_stats(locales)
    update(previous=True, ignore_obsolete=False)
    after = _snapshot_stats(locales)

    regressions: list[str] = []
    for locale in locales:
        before_stats = before.get(locale, CatalogStats())
        after_stats = after.get(locale, CatalogStats())

        if after_stats.translated < before_stats.translated:
            regressions.append(
                f"{locale}: translated entries decreased ({before_stats.translated} -> {after_stats.translated})"
            )

        if after_stats.fuzzy > before_stats.fuzzy:
            print(
                "Warning:",
                f"{locale} fuzzy entries increased ({before_stats.fuzzy} -> {after_stats.fuzzy})",
            )

    if regressions and not allow_translation_drop:
        print("\nUpdate blocked: translation regressions detected.")
        for item in regressions:
            print(" -", item)
        print(
            "\nIf this drop is expected for a specific refactor, rerun with "
            "--allow-translation-drop and review the diff carefully."
        )
        raise RuntimeError(TRANSLATION_REGRESSION_ERROR)


def compile_catalogs() -> None:
    """Compile PO files into MO files."""
    run([BABEL_CMD, "compile", "--domain", DOMAIN, "--directory", str(LOCALES_DIR)])


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Manage gettext translations with pybabel.")
    parser.add_argument(
        "command",
        choices=["extract", "init", "update", "prune-obsolete", "compile", "all"],
        help="Translation workflow command.",
    )
    parser.add_argument(
        "--locales",
        nargs="+",
        default=DEFAULT_LOCALES,
        help="Locales to initialize or update (default: common plugin locales).",
    )
    parser.add_argument(
        "--allow-translation-drop",
        action="store_true",
        help="Allow update even if translated entry counts decrease.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    try:
        if args.command == "extract":
            extract()
        elif args.command == "init":
            extract()
            init()
        elif args.command == "update":
            extract()
            safe_update(allow_translation_drop=args.allow_translation_drop)
        elif args.command == "prune-obsolete":
            extract()
            print("  -> Pruning obsolete entries (this can drop old fallback translations).")
            update(previous=True, ignore_obsolete=True)
        elif args.command == "compile":
            compile_catalogs()
        elif args.command == "all":
            extract()
            init()
            safe_update(allow_translation_drop=args.allow_translation_drop)
            compile_catalogs()

    except FileNotFoundError:
        print("Babel is not available. Install it with: pip install Babel")
        return 1
    except subprocess.CalledProcessError as exc:
        print(f"Translation command failed with code {exc.returncode}")
        return exc.returncode
    except RuntimeError as exc:
        print(str(exc))
        return 1

    print("Done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
