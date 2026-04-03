import pytest

from gusnet.i18n import set_locale, tr


@pytest.fixture
def locale():
    return "en"


@pytest.fixture
def translator(locale):
    set_locale(locale)
    return


@pytest.mark.parametrize(
    ("num_hours", "expected_message"),
    [
        (1, "1 hour"),
        (2, "2 hours"),
    ],
)
def test_numerus_translation_hours(num_hours, expected_message, translator):
    translated_message = tr("%n hour(s)", "", num_hours)

    assert translated_message == expected_message


@pytest.mark.parametrize(
    ("num_features", "expected_message"),
    [
        (1, "1 hour"),
        (2, "2 hours"),
    ],
)
def test_numerus_translation(num_features, expected_message, translator):
    translated_message = tr("%n hour(s)", "", num_features)

    assert translated_message == expected_message


@pytest.mark.parametrize(
    ("num_pipes", "expected_message"),
    [
        (1, "1 pipe has very different attribute length vs measured length. First five are: "),
        (2, "2 pipes have very different attribute length vs measured length. First five are: "),
    ],
)
def test_numerus_translation_pipes(num_pipes, expected_message, translator):
    translated_message = tr(
        "%n pipe(s) have very different attribute length vs measured length. First five are: ",
        "",
        num_pipes,
    )

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
def test_run_simulation_translation(locale, expected_message):
    set_locale(locale)
    translated_message = tr("Run Simulation")

    assert translated_message == expected_message
