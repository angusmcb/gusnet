.PHONY: init extract update compile translate

I18N_DIR = gusnet/resources/i18n
POT_FILE = $(I18N_DIR)/messages.pot

init:
	pybabel init -i $(POT_FILE) -d $(I18N_DIR) -l $(LANG)

extract:
	pybabel extract --add-location=file --omit-header -F babel.cfg -o $(POT_FILE) .

update: extract
	pybabel update --ignore-pot-creation-date -i $(POT_FILE) -d $(I18N_DIR)

compile:
	pybabel compile -d $(I18N_DIR)

translate: update compile
