import pytest

from gusnet.wntr_wrapper import WntrWrapper

pytestmark = [pytest.mark.needs_wntr]


def test_describe_network_counts():
    from wntr.network import WaterNetworkModel

    wn = WaterNetworkModel()
    wn.add_junction("j1", base_demand=0, elevation=0)
    wn.add_junction("j2", base_demand=0, elevation=0)
    wn.add_tank("t1", elevation=0, init_level=10, min_level=0, max_level=20, diameter=10, min_vol=0)
    wn.add_pipe("p1", "j1", "j2", length=100, diameter=10, roughness=100, minor_loss=0)
    wn.add_pipe("p2", "j2", "t1", length=100, diameter=10, roughness=100, minor_loss=0)
    wn.add_pipe("p3", "t1", "j1", length=100, diameter=10, roughness=100, minor_loss=0)
    wn.add_pipe("p4", "j1", "t1", length=100, diameter=10, roughness=100, minor_loss=0)
    wn.add_pipe("p5", "j2", "j1", length=100, diameter=10, roughness=100, minor_loss=0)
    wn.add_valve("v1", "j1", "j2", diameter=10, valve_type="PRV", initial_setting=10)
    wn.add_pump("p1", "j1", "j2", pump_type="POWER", pump_parameter=10)
    wn.add_pump("p2", "j2", "j1", pump_type="POWER", pump_parameter=10)

    html, text = WntrWrapper(wn).describe_network()
    # Should only include nonzero counts
    assert "2 Junctions" in text
    assert "1 Tanks" in text
    assert "5 Pipes" in text
    assert "1 Pressure Reducing Valve" in text
    assert "2 Pumps defined by power" in text
    assert "Pumps defined by head curve" not in text

    assert isinstance(html, str)


def test_describe_network_all_zero():
    from wntr.network import WaterNetworkModel

    wn = WaterNetworkModel()
    html, text = WntrWrapper(wn).describe_network()
    # Should be empty string if all counts are zero
    assert "Network Summary" in text
    assert isinstance(html, str)


def test_describe_network_all_types():
    from wntr.network import WaterNetworkModel

    wn = WaterNetworkModel()
    wn.add_junction("j1", base_demand=0, elevation=0)
    wn.add_junction("j2", base_demand=0, elevation=0)
    wn.add_tank("t1", elevation=0, init_level=10, min_level=0, max_level=20, diameter=10, min_vol=0)
    wn.add_reservoir("r1", base_head=100)
    wn.add_pipe("p1", "j1", "t1", length=100, diameter=10, roughness=100, minor_loss=0)
    wn.add_valve("v1", "j1", "j2", diameter=10, valve_type="PRV", initial_setting=10)
    wn.add_valve("v2", "j2", "j1", diameter=10, valve_type="PSV", initial_setting=10)
    wn.add_valve("v3", "j1", "r1", diameter=10, valve_type="PBV", initial_setting=10)
    wn.add_valve("v4", "j2", "j1", diameter=10, valve_type="FCV", initial_setting=10)
    wn.add_valve("v5", "t1", "r1", diameter=10, valve_type="TCV", initial_setting=10)
    wn.add_curve("c1", "HEAD", [(1, 2), (3, 4)])
    wn.add_valve("v6", "r1", "t1", diameter=10, valve_type="GPV", initial_setting="c1")
    wn.add_pump("p1", "j1", "t1", pump_type="POWER", pump_parameter=10)
    wn.add_pump("p2", "t1", "j1", pump_type="HEAD", pump_parameter="")

    html, text = WntrWrapper(wn).describe_network()
    # All types should be present
    assert "2 Junctions" in text
    assert "1 Tanks" in text
    assert "1 Reservoirs" in text
    assert "1 Pipes" in text
    assert "1 Pressure Reducing Valve" in text
    assert "1 Pressure Sustaining Valve" in text
    assert "1 Pressure Breaking Valve" in text
    assert "1 Flow Control Valve" in text
    assert "1 Throttle Control Valve" in text
    assert "1 General Purpose Valve" in text
    assert "1 Pumps defined by power" in text
    assert "1 Pumps defined by head curve" in text

    assert isinstance(html, str)


def test_describe_pipes_basic():
    from wntr.network import WaterNetworkModel

    wn = WaterNetworkModel()
    wn.options.hydraulic.inpfile_units = "LPS"  # Set units to Liters per Second
    wn.add_junction("j1", base_demand=0, elevation=0)
    wn.add_junction("j2", base_demand=0, elevation=0)
    wn.add_pipe("p1", "j1", "j2", length=100, diameter=10, roughness=100, minor_loss=0)
    wn.add_pipe("p2", "j2", "j1", length=200, diameter=10, roughness=110, minor_loss=0)
    wn.add_pipe("p3", "j1", "j2", length=300, diameter=20, roughness=120, minor_loss=0)

    html, text = WntrWrapper(wn).describe_pipes()
    # Check that the text alternative includes the total pipe length
    assert "Total pipe length" in text
    assert "600" in text  # Should match total length
    # Check that the HTML table includes expected diameters and roughness values
    assert "10" in html
    assert "20" in html
    assert "100" in html or "110" in html or "120" in html


@pytest.mark.filterwarnings("ignore:Changing the headloss formula")
def test_describe_pipes_conv():
    import wntr

    wn = wntr.network.WaterNetworkModel()
    wn.options.hydraulic.inpfile_units = "GPM"  # Set units to Liters per Second
    wn.options.hydraulic.headloss = "D-W"
    wn.add_junction("j1", base_demand=0, elevation=0)
    wn.add_junction("j2", base_demand=0, elevation=0)
    wn.add_pipe("p1", "j1", "j2", length=100, diameter=10, roughness=1, minor_loss=0)
    wn.add_pipe("p2", "j2", "j1", length=200, diameter=10, roughness=1, minor_loss=0)
    wn.add_pipe("p3", "j1", "j2", length=300, diameter=20, roughness=1, minor_loss=0)

    html, text = WntrWrapper(wn).describe_pipes()
    # Check that the text alternative includes the total pipe length
    assert "Total pipe length" in text
    assert "1 968.50" in text  # Should match total length
    # Check that the HTML table includes expected diameters and roughness values
    assert "393" in html
    assert "787" in html

    if wntr.__version__ == "1.2.0":
        pytest.skip(reason="Roughness conversion broken in wntr 1.2.0")

    assert "3 281" in html  # roughness in 1/1000 feeet - doesn't work in wntr 1.2.0


def test_describe_pipes_empty():
    from wntr.network import WaterNetworkModel

    wn = WaterNetworkModel()
    html, text = WntrWrapper(wn).describe_pipes()
    assert "Total pipe length" in text
    assert "0.00" in text or "0" in text
    assert "<table" in html
    assert "No pipes" not in html  # Should still render a table, even if empty
