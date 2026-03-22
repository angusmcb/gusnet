import pytest


@pytest.fixture(scope="session", autouse=True)
def only_run_if_wntr_available():
    try:
        import wntr  # noqa: F401
    except ImportError:
        pytest.skip("WNTR is not available, skipping tests that require WNTR.", allow_module_level=True)
