---
description: "Use when updating gettext translations, editing PO/POT files, handling fuzzy matches, or running translation updates in gusnet/resources/i18n."
name: "Translation Workflow Rules"
applyTo: "gusnet/resources/i18n/**/*.po"
---
# Translation Workflow Rules

## Role
- You are the translator. Translate strings directly into the target language by editing the PO file yourself.
- Do not write scripts or use automation to perform translations. Do not delegate translation to external tools or code.
- Use your knowledge as a large language model to produce accurate, natural-sounding translations directly in the file.

## Running Makefile targets
- `pybabel` must be on PATH. Try `PATH="<workspace>/conda2/bin:$PATH" make <target>` if it is not already available.
- Read the Makefile to understand what translation workflow commands are available.

## Workflow for updating existing locales
1. Run `make translate` to extract, update, and compile all existing locale catalogs.
2. Check for untranslated or fuzzy entries after the update and translate them directly in the PO file.
3. Run `make compile` to recompile after editing.

## Workflow for adding a new locale
1. Run `make init LANG=<locale>` to create the new catalog.
2. Open the new PO file and translate all msgstr entries directly, working through the file in sections using `read_file` and `apply_patch` or `replace_string_in_file`.
3. Read large sections of the file (300–500 lines at a time), identify all empty or malformed msgstr entries, and apply a batch of edits in one patch per section.
4. After completing all sections, run `make compile` to validate and generate the `.mo` file.

## Translation rules
- Treat fuzzy entries as review-required content.
- Do not clear fuzzy status mechanically. Confirm semantic meaning in the target language before finalizing msgstr.
- If an entry has been corrected, remove stale previous-source comment lines that start with #| msgid for that entry.
- Also add translations for new msgid entries that do not yet have translations.
- Do not use English in any msgstr in non-English locale catalogs. If a translation is not yet available, leave the msgstr empty. Only use English if it is the same in the target language (e.g. for technical terms or brand names that do not change across locales).
- Keep msgstr formatting consistent with msgid punctuation and line-break intent.
- If msgid does not end with a newline marker, do not leave a trailing newline escape in msgstr.
- Preserve placeholders and formatting tokens exactly, including python-brace-format placeholders (e.g. {error_code}, {layer}, {count}).
- For plural forms, provide the appropriate msgstr[0] (and msgstr[1] if the target language distinguishes plural) — never leave plural slots empty.
- Do not mix English and the target language within a single msgstr. Replace the entire string.

## Validation
- After edits, compile the catalog to confirm it parses cleanly. A successful compile (no errors printed) is the validation step.
- Check for remaining empty entries with: `grep -c '^msgstr ""$' <file>`
- Check for fuzzy markers with: `grep -n '#, fuzzy' <file>`
