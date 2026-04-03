from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DOMAIN = "gusnet"
BABEL_CONFIG = ROOT / "babel.cfg"
SOURCE_DIR = ROOT / "gusnet"
I18N_ROOT = SOURCE_DIR / "resources" / "i18n"
LOCALES_DIR = I18N_ROOT / "locales"
TEMPLATE_PATH = I18N_ROOT / "messages.pot"
DEFAULT_LOCALES = ["ar", "de", "en", "es", "fr", "it", "nl", "pt"]
BABEL_CMD = "pybabel"


def run(cmd: list[str]) -> None:
    print("  ->", " ".join(cmd))
    subprocess.run(cmd, check=True)  # noqa: S603


def extract() -> None:
    """Extract translatable strings to the POT template."""
    LOCALES_DIR.mkdir(parents=True, exist_ok=True)
    run(
        [
            "pybabel",
            "extract",
            "--mapping-file",
            str(BABEL_CONFIG),
            "--output-file",
            str(TEMPLATE_PATH),
            ".",
        ]
    )


def init(locales: list[str]) -> None:
    """Initialize missing locale catalogs from the POT template."""
    for locale in locales:
        po_path = LOCALES_DIR / locale / "LC_MESSAGES" / f"{DOMAIN}.po"
        if po_path.exists():
            print(f"  -> Skipping existing locale: {locale}")
            continue

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


def update(locales: list[str]) -> None:
    """Update existing locale catalogs from the POT template."""
    locale_args: list[str] = []
    for locale in locales:
        locale_args.extend(["--locale", locale])

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
            *locale_args,
        ]
    )


def compile_catalogs() -> None:
    """Compile PO files into MO files."""
    run([BABEL_CMD, "compile", "--domain", DOMAIN, "--directory", str(LOCALES_DIR)])


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Manage gettext translations with pybabel.")
    parser.add_argument(
        "command",
        choices=["extract", "init", "update", "compile", "all"],
        help="Translation workflow command.",
    )
    parser.add_argument(
        "--locales",
        nargs="+",
        default=DEFAULT_LOCALES,
        help="Locales to initialize or update (default: common plugin locales).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    try:
        if args.command == "extract":
            extract()
        elif args.command == "init":
            extract()
            init(args.locales)
        elif args.command == "update":
            extract()
            update(args.locales)
        elif args.command == "compile":
            compile_catalogs()
        elif args.command == "all":
            extract()
            init(args.locales)
            update(args.locales)
            compile_catalogs()

    except FileNotFoundError:
        print("Babel is not available. Install it with: pip install Babel")
        return 1
    except subprocess.CalledProcessError as exc:
        print(f"Translation command failed with code {exc.returncode}")
        return exc.returncode

    print("Done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
