---
description: "Use when updating gettext translations, editing PO/POT files, handling fuzzy matches, or running translation updates in gusnet/resources/i18n."
name: "Translation Workflow Rules"
applyTo: "gusnet/resources/i18n/**/*.po"
---
# Translation Workflow Rules

- You are to act as a translator and editor for gettext translation files.
- Treat fuzzy entries as review-required content.
- Do not clear fuzzy status mechanically. Confirm semantic meaning in the target language before finalizing msgstr.
- If an entry has been corrected, remove stale previous-source comment lines that start with #| msgid for that entry.
- Also add translations for new msgid entries that do not yet have translations.
- Do not use English in any msgstr in non-English locale catalogs. If a translation is not yet available, leave the msgstr empty. Only use English if it is the same in the target language (e.g. for technical terms or brand names that do not change across locales).
- Keep msgstr formatting consistent with msgid punctuation and line-break intent.
- If msgid does not end with a newline marker, do not leave a trailing newline escape in msgstr.
- Preserve placeholders and formatting tokens exactly, including python-brace-format placeholders.
- After edits, validate catalogs parse cleanly before finishing.
- Prefer a parser-based validation step for PO syntax and consistency.
- Ensure all *.po files finish with exactly one newline character at the end of the file.
