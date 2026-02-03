import pytest
from qgis.core import QgsVectorLayer

from gusnet.elements import DEFAULT_OPTIONS, FieldGroup
from gusnet.wntr_wrapper import WntrWrapper, _get_field_groups

pytestmark = [pytest.mark.needs_wntr]


@pytest.fixture
def wn():
    import wntr

    return wntr.network.WaterNetworkModel()


@pytest.fixture
def qgs_layer():
    return QgsVectorLayer("Point", "test_layer", "memory")


def test_get_field_groups(wn):
    assert _get_field_groups(DEFAULT_OPTIONS) == FieldGroup(0)

    wn.options.quality.parameter = "CHEMICAL"
    wn.options.report.energy = "YES"

    options = WntrWrapper(wn).options

    field_groups = _get_field_groups(options)

    assert field_groups == FieldGroup.ENERGY | FieldGroup.WATER_QUALITY_ANALYSIS
