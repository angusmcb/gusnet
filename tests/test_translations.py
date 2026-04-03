import pytest

from gusnet.i18n import set_locale, tr, trn


@pytest.fixture
def locale():
    return "en"


@pytest.fixture
def translator(locale):
    set_locale(locale)
    yield
    set_locale(None)
    return


@pytest.mark.parametrize(
    ("num_features", "expected_message"),
    [
        (1, "1 hour"),
        (2, "2 hours"),
    ],
)
def test_numerus_translation(num_features, expected_message, translator):
    translated_message = trn("1 hour", "{count} hours", num_features)

    assert translated_message == expected_message


@pytest.mark.parametrize(
    ("locale", "expected_message"),
    [
        ("en", "Run Simulation"),
        ("es", "Ejecutar simulación"),
        ("fr", "Exécuter la simulation"),
        ("de", "Simulation ausführen"),
        ("it", "Esegui simulazione"),
        ("pt", "Executar Simulação"),
        ("ar", "تشغيل المحاكاة"),
    ],
)
def test_run_simulation_translation(translator, expected_message):
    translated_message = tr("Run Simulation")

    assert translated_message == expected_message
