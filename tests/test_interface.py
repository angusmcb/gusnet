import pytest
from qgis.core import QgsVectorLayer

import gusnet.elements
from gusnet.interface import WntrModel


@pytest.fixture
def wn():
    import wntr

    return wntr.network.WaterNetworkModel()


@pytest.fixture
def qgs_layer():
    return QgsVectorLayer("Point", "test_layer", "memory")


def test_get_field_groups(wn):
    from gusnet.elements import DefaultOptions, FieldGroup

    assert gusnet.interface._get_field_groups(DefaultOptions()) == FieldGroup(0)

    wn.options.quality.parameter = "CHEMICAL"
    wn.options.report.energy = "YES"
    wn.options.hydraulic.demand_model = "PDD"

    options = WntrModel(wn).options

    field_groups = gusnet.interface._get_field_groups(options)

    assert field_groups == FieldGroup.PRESSURE_DEPENDENT_DEMAND | FieldGroup.ENERGY | FieldGroup.WATER_QUALITY_ANALYSIS
