import re
from pathlib import Path

import pytest
from pandas.testing import assert_frame_equal
from qgis.core import QgsProcessingException, QgsProcessingFeedback, QgsProject, QgsVectorLayer

from gusnet.gusnet_processing.empty_model import TemplateLayers
from gusnet.gusnet_processing.import_inp import ImportInp
from gusnet.gusnet_processing.run_simulation import ExportInpFile, RunSimulation


# the examples are store in the plugin folder as they are used in the plugin
@pytest.fixture(scope="module")
def example_dir():
    return Path(__file__).parent.parent / "gusnet" / "resources" / "examples"


@pytest.fixture
def template_alg():
    return TemplateLayers().create()


@pytest.fixture
def import_alg():
    return ImportInp().create()


@pytest.fixture
def run_alg():
    return RunSimulation().create()


@pytest.fixture
def export_alg():
    return ExportInpFile().create()


@pytest.fixture
def crs():
    return "EPSG:32629"


@pytest.fixture
def output_type():
    return "TEMPORARY_OUTPUT"


@pytest.fixture
def template_alg_params(crs, output_file):
    return {
        "CRS": crs,
        "JUNCTIONS": output_file(),
        "PIPES": output_file(),
        "PUMPS": output_file(),
        "RESERVOIRS": output_file(),
        "TANKS": output_file(),
        "VALVES": output_file(),
    }


@pytest.fixture
def template_result(processing, template_alg, template_alg_params):
    return processing.run(template_alg, template_alg_params)


@pytest.fixture
def inp():
    return "ky1.inp"


@pytest.fixture
def inp_file(inp, example_dir):
    return str(example_dir / inp)


@pytest.fixture
def import_alg_params(template_alg_params, inp_file):
    template_alg_params["INPUT"] = inp_file
    template_alg_params["UNITS"] = 0
    return template_alg_params


@pytest.fixture
def import_layers(processing, import_alg, import_alg_params):
    return processing.run(import_alg, import_alg_params)


@pytest.fixture
def feedback():
    class TestFeedback(QgsProcessingFeedback):
        def pushWarning(self, msg):  # noqa: N802
            if not hasattr(self, "warnings"):
                self.warnings = []
            self.warnings.append(msg)

    return TestFeedback()


@pytest.fixture
def duration():
    return 0


@pytest.fixture
def run_alg_params(import_layers, duration):
    return {
        "RESULT_NODES": "TEMPORARY_OUTPUT",
        "RESULT_LINKS": "TEMPORARY_OUTPUT",
        "OUTPUT_INP": "TEMPORARY_OUTPUT",
        "UNITS": 0,
        "HEADLOSS_FORMULA": 0,
        "DURATION": duration,
        **import_layers,
    }


@pytest.fixture
def run_result(processing, run_alg, run_alg_params, feedback):
    return processing.run(
        run_alg,
        run_alg_params,
        feedback=feedback,
    )


@pytest.fixture
def export_result(processing, export_alg, run_alg_params, feedback):
    return processing.run(
        export_alg,
        run_alg_params,
        feedback=feedback,
    )


@pytest.fixture
def output_file(tmp_path, output_type):
    i = 0

    def get_file_string():
        nonlocal i
        i += 1
        if output_type == "TEMPORARY_OUTPUT":
            return "TEMPORARY_OUTPUT"
        if output_type == "gpkg":
            return "ogr:dbname='" + str(tmp_path / "outputs.gpkg") + "' table=\"" + str(i) + '" (geom)'
        if output_type == "shp":
            return str(tmp_path / (str(i) + ".shp"))
        if output_type == "geojson":
            return str(tmp_path / (str(i) + ".geojson"))
        msg = "Unknown file type"
        raise ValueError(msg)

    return get_file_string


def test_display_name_import_inp(import_alg):
    assert import_alg.displayName() == "Import from Epanet INP file"


def test_display_name_run_simulation(run_alg):
    assert run_alg.displayName() == "Run Simulation"


def test_display_name_template_layers(template_alg):
    assert template_alg.displayName() == "Create Template Layers"


def test_display_name_export_inp(export_alg):
    assert export_alg.displayName() == "Export Inp File"


def test_icon_import_inp(import_alg, assert_valid_qicon):
    icon = import_alg.icon()
    assert_valid_qicon(icon)


def test_icon_run_simulation(run_alg, assert_valid_qicon):
    icon = run_alg.icon()
    assert_valid_qicon(icon)


def test_icon_template_layers(template_alg, assert_valid_qicon):
    icon = template_alg.icon()
    assert_valid_qicon(icon)


def test_icon_export_inp(export_alg, assert_valid_qicon):
    icon = export_alg.icon()
    assert_valid_qicon(icon)


def test_name_import_inp(import_alg):
    assert import_alg.name() == "import_inp"


def test_name_run_simulation(run_alg):
    assert run_alg.name() == "run"


def test_name_template_layers(template_alg):
    assert template_alg.name() == "template_layers"


def test_name_export_inp(export_alg):
    assert export_alg.name() == "export"


def test_help_import_inp(import_alg):
    help_string = import_alg.shortHelpString()
    assert isinstance(help_string, str)
    assert help_string


def test_help_run_simulation(run_alg):
    help_string = run_alg.shortHelpString()
    assert isinstance(help_string, str)
    assert help_string


def test_help_template_layers(template_alg):
    help_string = template_alg.shortHelpString()
    assert isinstance(help_string, str)
    assert help_string


def test_help_export_inp(export_alg):
    help_string = export_alg.shortHelpString()
    assert isinstance(help_string, str)
    assert help_string


def test_template_layers(template_result):
    assert list(template_result.keys()) == ["JUNCTIONS", "PIPES", "PUMPS", "RESERVOIRS", "TANKS", "VALVES"]


def test_import_layers(import_layers):
    assert list(import_layers.keys()) == ["JUNCTIONS", "PIPES", "PUMPS", "RESERVOIRS", "TANKS", "VALVES"]


def test_load_template_layers(processing, qgis_new_project, template_alg, template_alg_params):
    """This also implicitly checks the styling"""
    processing.runAndLoadResults(template_alg, template_alg_params)

    assert len(QgsProject.instance().mapLayers()) == 6


@pytest.mark.parametrize(
    "inp", ["ky1.inp", "ky10.inp", "ky17.inp", "Net3.simplified.inp", "valves.inp", "single_pipe_warning.inp"]
)
def test_alg_import_inp_all_examples(processing, import_alg, import_alg_params, qgis_new_project):
    processing.runAndLoadResults(import_alg, import_alg_params)

    assert len(QgsProject.instance().mapLayers()) == 6


def test_template_layers_junctions(template_result):
    assert template_result["JUNCTIONS"].fields().names() == [
        "name",
        "elevation",
        "base_demand",
        "demand_pattern",
        "emitter_coefficient",
    ]


def test_import_layers_junctions(import_layers):
    assert import_layers["JUNCTIONS"].fields().names() == [
        "name",
        "elevation",
        "base_demand",
        "demand_pattern",
        "emitter_coefficient",
        "initial_quality",
    ]


def test_template_layers_tanks(template_result):
    assert template_result["TANKS"].fields().names() == [
        "name",
        "elevation",
        "init_level",
        "min_level",
        "max_level",
        "tank_diameter",
        "min_vol",
        "vol_curve",
        "overflow",
    ]


def test_import_layers_tanks(import_layers):
    assert import_layers["TANKS"].fields().names() == [
        "name",
        "elevation",
        "init_level",
        "min_level",
        "max_level",
        "tank_diameter",
        "min_vol",
        "vol_curve",
        "overflow",
        "initial_quality",
        "mixing_model",
        "mixing_fraction",
        "bulk_coeff",
    ]


def test_template_layers_reservoirs(template_result):
    assert template_result["RESERVOIRS"].fields().names() == ["name", "base_head", "head_pattern"]


def test_import_layers_reservoirs(import_layers):
    assert import_layers["RESERVOIRS"].fields().names() == ["name", "base_head", "head_pattern", "initial_quality"]


def test_template_layers_pipes(template_result):
    assert template_result["PIPES"].fields().names() == [
        "name",
        "diameter",
        "length",
        "roughness",
        "minor_loss",
        "check_valve",
        "initial_status",
    ]


def test_import_layers_pipes(import_layers):
    assert import_layers["PIPES"].fields().names() == [
        "name",
        "diameter",
        "length",
        "roughness",
        "minor_loss",
        "check_valve",
        "initial_status",
        "bulk_coeff",
        "wall_coeff",
    ]


def test_template_layers_pumps(template_result):
    assert template_result["PUMPS"].fields().names() == [
        "name",
        "pump_type",
        "pump_curve",
        "power",
        "base_speed",
        "speed_pattern",
        "initial_status",
    ]


def test_import_layers_pumps(import_layers):
    assert import_layers["PUMPS"].fields().names() == [
        "name",
        "pump_type",
        "pump_curve",
        "power",
        "base_speed",
        "speed_pattern",
        "initial_status",
    ]


def test_template_layers_valves(template_result):
    assert template_result["VALVES"].fields().names() == [
        "name",
        "valve_type",
        "pressure_setting",
        "flow_setting",
        "throttle_setting",
        "headloss_curve",
        "diameter",
        "minor_loss",
        "valve_status",
    ]


def test_import_layers_valves(import_layers):
    assert import_layers["VALVES"].fields().names() == [
        "name",
        "valve_type",
        "pressure_setting",
        "flow_setting",
        "throttle_setting",
        "headloss_curve",
        "diameter",
        "minor_loss",
        "valve_status",
    ]


def test_alg_template_layers_water_quality(processing, template_alg, template_alg_params):
    template_alg_params["WATER_QUALITY_ANALYSIS"] = True

    result = processing.run(template_alg, template_alg_params)

    assert "initial_quality" in result["JUNCTIONS"].fields().names()
    assert "initial_quality" in result["TANKS"].fields().names()
    assert "initial_quality" in result["RESERVOIRS"].fields().names()

    assert "mixing_fraction" in result["TANKS"].fields().names()
    assert "mixing_model" in result["TANKS"].fields().names()
    assert "bulk_coeff" in result["TANKS"].fields().names()

    assert "bulk_coeff" in result["PIPES"].fields().names()
    assert "wall_coeff" in result["PIPES"].fields().names()


def test_alg_template_layers_pressure_dependent_demand(processing, template_alg, template_alg_params):
    template_alg_params["PRESSURE_DEPENDENT_DEMAND"] = True

    result = processing.run(template_alg, template_alg_params)

    assert "required_pressure" in result["JUNCTIONS"].fields().names()
    assert "minimum_pressure" in result["JUNCTIONS"].fields().names()
    assert "pressure_exponent" in result["JUNCTIONS"].fields().names()


def test_alg_template_layers_energy(processing, template_alg, template_alg_params):
    template_alg_params["ENERGY"] = True

    result = processing.run(template_alg, template_alg_params)

    assert "efficiency_curve" in result["PUMPS"].fields().names()
    assert "energy_pattern" in result["PUMPS"].fields().names()
    assert "energy_price" in result["PUMPS"].fields().names()


def test_alg_import_inp_bad_inp(processing, import_alg, import_alg_params, bad_inp):
    import_alg_params["INPUT"] = bad_inp

    with pytest.raises(QgsProcessingException, match="error reading .inp file:"):
        processing.run(import_alg, import_alg_params)


def test_alg_import_inp_no_file(processing, import_alg, import_alg_params):
    import_alg_params["INPUT"] = "doesnt_exist.inp"

    with pytest.raises(QgsProcessingException, match="inp file does not exist"):
        processing.run(import_alg, import_alg_params)


def test_alg_import_inp_no_unit(processing, import_alg, import_alg_params):
    import_alg_params["UNITS"] = None

    processing.run(import_alg, import_alg_params)

    # how to check that the units are set correctly?


def test_alg_import_inp_bad_units(processing, import_alg, import_alg_params):
    import_alg_params["UNITS"] = 19

    with pytest.raises(QgsProcessingException, match="Incorrect parameter value for UNITS"):
        processing.run(import_alg, import_alg_params)


def test_alg_import_inp_preprocess(processing, import_alg, import_alg_params):
    example = "ky1.inp"
    import_alg_params["INPUT"] = example
    processed_params = import_alg.preprocessParameters(import_alg_params)

    assert example in processed_params["INPUT"]
    assert Path(processed_params["INPUT"]).is_file()


@pytest.mark.parametrize(
    "inp",
    [
        "ky1.inp",
        "ky10.inp",
        pytest.param("ky17.inp", marks=pytest.mark.skip()),
        "Net3.simplified.inp",
        "valves.inp",
        "single_pipe_warning.inp",
    ],
)
def test_run_example_inps(run_result):
    assert list(run_result.keys()) == ["RESULT_LINKS", "RESULT_NODES"]
    assert isinstance(run_result["RESULT_NODES"], QgsVectorLayer)
    assert isinstance(run_result["RESULT_LINKS"], QgsVectorLayer)


def test_run_node_fields(run_result):
    assert run_result["RESULT_NODES"].fields().names() == ["name", "demand", "head", "pressure", "quality"]


def test_run_link_fields(run_result):
    assert run_result["RESULT_LINKS"].fields().names() == [
        "name",
        "flowrate",
        "headloss",
        "unit_headloss",
        "velocity",
        "quality",
        "reaction_rate",
    ]


@pytest.mark.parametrize("duration", [-1])
def test_run_negative_duration(processing, run_alg, run_alg_params):
    with pytest.raises(QgsProcessingException, match="Incorrect parameter value for DURATION"):
        processing.run(run_alg, run_alg_params)


def test_run_no_junctions(processing, run_alg, run_alg_params):
    del run_alg_params["JUNCTIONS"]
    with pytest.raises(
        QgsProcessingException, match="Could not load source layer for JUNCTIONS: no value specified for parameter"
    ):
        processing.run(run_alg, run_alg_params)


@pytest.mark.parametrize("inp", ["single_pipe_warning.inp"])
def test_epanet_warning(run_result, feedback):
    expected_warning = "EPANET warning 6 - At   0:00:00, system has negative pressures - negative pressures occurred at one or more junctions with positive demand"  # noqa: E501
    assert expected_warning in feedback.warnings


@pytest.mark.parametrize("inp", ["single_pipe_warning.inp"])
def test_pipe_length_warning(run_result, feedback):
    expected_warning = r"1 pipe.*3618 metres vs 305 metres"

    assert any(re.search(expected_warning, s) for s in feedback.warnings), list(feedback.warnings)


@pytest.mark.parametrize(("inp", "duration"), [("Net3.simplified.inp", 24), ("valves.inp", 0)])
@pytest.mark.parametrize("output_type", ["TEMPORARY_OUTPUT", "gpkg", "geojson", "shp"])
def test_inp_results_match(export_result, inp_file):
    import wntr

    wn = wntr.network.read_inpfile(inp_file)
    in_results = wntr.sim.EpanetSimulator(wn).run_sim()

    wn = wntr.network.read_inpfile(export_result["OUTPUT_INP"])
    out_results = wntr.sim.EpanetSimulator(wn).run_sim()

    assert_frame_equal(in_results.node["demand"], out_results.node["demand"], rtol=0.005)

    assert_frame_equal(in_results.node["head"], out_results.node["head"], rtol=0.005)

    assert_frame_equal(in_results.node["pressure"], out_results.node["pressure"], rtol=0.005)

    assert_frame_equal(in_results.link["flowrate"], out_results.link["flowrate"], rtol=0.005, atol=1e-04)

    assert_frame_equal(in_results.link["headloss"], out_results.link["headloss"], rtol=0.005, atol=1e-04)

    assert_frame_equal(in_results.link["velocity"], out_results.link["velocity"], rtol=0.005, atol=1e-04)


@pytest.mark.parametrize("crs", ["EPSG:4326", "EPSG:32629", "EPSG:3857"])
class TestDifferentCRS:
    def test_template_crs(self, template_result, crs):
        assert template_result["JUNCTIONS"].crs().authid() == crs

    def test_import_crs(self, import_layers, crs):
        assert import_layers["JUNCTIONS"].crs().authid() == crs


@pytest.mark.parametrize("crs", ["NOT_A_CRS"])
@pytest.mark.skip(reason="Need to create an error for this")
class TestWrongCRS:
    def test_template_crs(self, template_result, crs):
        assert template_result["JUNCTIONS"].crs().authid() == crs

    def test_import_crs(self, import_layers, crs):
        assert import_layers["JUNCTIONS"].crs().authid() == crs


class TestNoCRS:
    @pytest.fixture
    def crs(self):
        return None

    def test_template_crs(self, template_result):
        assert template_result["JUNCTIONS"].crs() == QgsProject.instance().crs()

    def test_alg_import_inp_with_no_crs(self, processing, import_alg, import_alg_params):
        with pytest.raises(QgsProcessingException, match="Incorrect parameter value for CRS"):
            processing.run(import_alg, import_alg_params)
