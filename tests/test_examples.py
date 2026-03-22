import pytest
from qgis.core import QgsVectorLayer

import gusnet

pytestmark = [pytest.mark.needs_wntr]


@pytest.fixture(params=gusnet.examples.values())
def example_wn(request):
    import wntr

    return wntr.network.WaterNetworkModel(request.param)


@pytest.mark.parametrize("example", gusnet.examples.values())
@pytest.mark.needs_pandas
def test_examples(example):
    import pandas as pd
    import wntr

    assert example.endswith(".inp")
    wn = wntr.network.WaterNetworkModel(example)
    assert wn
    sim = wntr.sim.EpanetSimulator(wn)
    results = sim.run_sim()
    assert isinstance(results.node["demand"], pd.DataFrame)


def test_from_wntr(example_wn, qgis_new_project):
    layers = gusnet.from_wntr(example_wn)
    assert isinstance(layers, dict)
    assert isinstance(layers["JUNCTIONS"], QgsVectorLayer)
    assert isinstance(layers["PIPES"], QgsVectorLayer)
    assert isinstance(layers["RESERVOIRS"], QgsVectorLayer)
    assert isinstance(layers["TANKS"], QgsVectorLayer)
    assert isinstance(layers["VALVES"], QgsVectorLayer)
    assert isinstance(layers["PUMPS"], QgsVectorLayer)

    assert layers["JUNCTIONS"].featureCount() > 2


def test_from_wntr_with_results(example_wn, qgis_new_project):
    import wntr

    sim = wntr.sim.EpanetSimulator(example_wn)
    results = sim.run_sim()
    layers = gusnet.from_wntr(example_wn, results)

    assert isinstance(layers, dict)
    assert isinstance(layers["LINKS"], QgsVectorLayer)
    assert isinstance(layers["NODES"], QgsVectorLayer)


def test_from_to_wntr_roundtrip(example_wn, qgis_new_project):
    layers = gusnet.from_wntr(example_wn)
    gusnet.to_wntr(layers, units="GPM", headloss_formula="H-W")


@pytest.mark.parametrize("example", gusnet.examples.values())
def test_read_inp(example, qgis_new_project):
    layers = gusnet.from_inp(example)

    assert isinstance(layers, dict)
    assert isinstance(layers["JUNCTIONS"], QgsVectorLayer)

    assert layers["JUNCTIONS"].featureCount() > 2
