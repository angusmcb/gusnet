from __future__ import annotations

from typing import TYPE_CHECKING, Callable

import pytest
from qgis.core import QgsProcessingProvider, QgsProcessingRegistry

from gusnet.gusnet_processing.provider import Provider

if TYPE_CHECKING:
    from qgis.PyQt.QtGui import QIcon


@pytest.fixture(scope="module")
def provider() -> Provider:
    provider = Provider()
    provider.refreshAlgorithms()
    return provider


def test_processing_provider(provider: Provider) -> None:
    assert isinstance(provider, QgsProcessingProvider)


def test_processing_provider_icon(provider: Provider, assert_valid_qicon: Callable[[QIcon], None]) -> None:
    icon = provider.icon()
    assert_valid_qicon(icon)


def test_processing_provider_name(provider: Provider) -> None:
    assert provider.name() == "Gusnet"


def test_processing_provider_id(provider: Provider) -> None:
    assert provider.id() == "gusnet"


@pytest.mark.parametrize("algorithm", ["import_inp", "run", "template_layers", "export"])
def test_processing_alg_loaded(algorithm: str, provider: Provider) -> None:
    assert provider.algorithm(algorithm)


def test_register_processing_provider(provider: Provider) -> None:
    registry = QgsProcessingRegistry()
    registry.addProvider(provider)
    assert provider in registry.providers()
    registry.removeProvider(provider)
