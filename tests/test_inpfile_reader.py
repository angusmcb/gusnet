import datetime
from pathlib import Path

import pytest

import gusnet
from gusnet.elements import HeadlossFormula
from gusnet.inpfile_reader import InpFileReadError, read_inp_file
from gusnet.pattern_curve import Pattern


@pytest.fixture
def write_inp(tmp_path):
    def _write_inp(content: str) -> Path:
        file_path = tmp_path / "test_model.inp"
        file_path.write_text(content)
        return file_path

    return _write_inp


@pytest.mark.parametrize("inp_file", gusnet.examples.values())
def test_example_inps(inp_file):
    model = read_inp_file(inp_file)
    assert model


def test_reads_without_errors(test_inp_dir):
    inp_path = test_inp_dir / "single_pipe_warning.inp"
    model = read_inp_file(inp_path)

    assert model.attributes
    assert model.network
    assert model.options


def test_errors_on_options_value_error(test_inp_dir):
    bad_inp = test_inp_dir / "bad_syntax.inp"
    with pytest.raises(InpFileReadError, match="NOT-A-HEADLOSS"):
        read_inp_file(bad_inp)


def test_error_on_non_existant_file(test_inp_dir):
    bad_inp = test_inp_dir / "this file does not exist.inp"

    with pytest.raises(InpFileReadError, match="this file does not exist"):
        read_inp_file(bad_inp)


def test_errors_on_no_pattern(write_inp):
    file = write_inp("""
[JUNCTIONS]
junction1                  0           12              PATTERN_DOESNT_EXIST
""")

    with pytest.raises(InpFileReadError, match="PATTERN_DOESNT_EXIST"):
        read_inp_file(file)


def test_no_network_in_inp(write_inp):
    file = write_inp(
        """
[JUNCTIONS]

[OPTIONS]
HEADLOSS H-W
"""
    )

    with pytest.raises(InpFileReadError, match="No valid sections"):
        read_inp_file(file)


def test_comments_in_inp(write_inp):
    file = write_inp(
        """; this is a comment
[OPTIONS]
; another comment
HEADLOSS H-W ; comment at end of line
; comment on its own line
[COORDINATES]
; comment before coordinates
J1 0 0 ; comment after coordinate
; comment after blank line
; [PIPES]
[JUNCTIONS]
; J2 0 0
J1 0 0 ; comment after junction"""
    )

    model = read_inp_file(file)

    assert model.attributes["JUNCTIONS"]["name"] == ("J1",)


def test_inp_options(write_inp):
    file = write_inp(
        """[JUNCTIONS]
J1 0 0
[PATTERNS]
PATTERN2 1 0.5 0.5 1
[OPTIONS]
HEADLOSS D-W
UNITS CFS
PRESSURE UNITS PSI
demand model PDA
quality chlorine
PATTERN PATTERN2
"""
    )

    model = read_inp_file(file)

    assert model.options.headloss_formula == HeadlossFormula.DARCY_WEISBACH
    assert model.options.flow_unit.name == "CFS"
    assert model.options.demand_type.name == "PRESSURE_DEPENDENT"
    assert model.options.quality_parameter.name == "CHEMICAL"
    assert model.options.default_pattern == Pattern((1.0, 0.5, 0.5, 1.0))


def test_inp_options_2(write_inp):
    file = write_inp(
        """[JUNCTIONS]
J55 0 0
[OPTIONS]
HEADLOSS D-W
quality trace J55
[PATTERNS]
1 0.5 0.5 1
"""
    )
    model = read_inp_file(file)
    assert model.options.quality_parameter.name == "TRACE"
    assert model.options.trace_node == "J55"
    assert model.options.default_pattern == Pattern((0.5, 0.5, 1.0))


def test_inp_options_error_on_headloss(write_inp):
    file = write_inp(
        """[JUNCTIONS]
J1 0 0
[OPTIONS]
HEADLOSS NOT-A-HEADLOSS
"""
    )
    with pytest.raises(InpFileReadError, match="NOT-A-HEADLOSS"):
        read_inp_file(file)


def test_inp_reactions(write_inp):
    file = write_inp(
        """[JUNCTIONS]
J1 0 0
[REACTIONS]
ORDER BULK 0.33
ORDER WALL 0
ORDER TANK 0.11
GLOBAL BULK 0.22
GLOBAL WALL 0.44
LIMITING POTENTIAL 0.55
ROUGHNESS CORRELATION 0.12
"""
    )
    model = read_inp_file(file)

    assert model.options.bulk_reaction_order == 0.33
    assert model.options.wall_reaction_order.value == 0
    assert model.options.global_bulk_coefficient == 0.22
    assert model.options.global_wall_coefficient == 0.44
    assert model.options.limiting_concentration == 0.55
    assert model.options.wall_coefficient_correlation == 0.12


def test_inp_reactions_wall_order_error(write_inp):
    file = write_inp(
        """[JUNCTIONS]
J1 0 0
[REACTIONS]
ORDER WALL 0.1
"""
    )

    with pytest.raises(InpFileReadError, match="Invalid wall reaction order value: 0.1"):  # noqa: RUF043
        read_inp_file(file)


def test_reactions_wall_tank_specific(write_inp):
    file = write_inp(
        """[TANKS]
T1 0 0 100 0 0
T2 0 0 100 0 0
[PIPES]
;ID   Node1  Node2   Length   Diam.  Roughness  Mloss   Status
;-------------------------------------------------------------
P1    J1     J2     1200      12      120       0.2     OPEN
P2    J3     J2      600       6      110       0       CV
P3    J1     J10    1000      12      120
[REACTIONS]
TANK T1 0.11
BULK P1 0.22
WALL P2 0.33
"""
    )
    model = read_inp_file(file)
    assert model.attributes["TANKS"]["bulk_coeff"] == [0.11, 0.0]
    assert model.attributes["PIPES"]["bulk_coeff"] == [0.22, 0.0, 0.0]
    assert model.attributes["PIPES"]["wall_coeff"] == [0.0, 0.33, 0.0]


@pytest.mark.parametrize(
    "duration", ["7200 SECONDS", "7200 SEC", "120 MINUTES", "120 MIN", "2 HOURS", f"{2 / 24} DAYS", "2.0", "2:00"]
)
def test_times_duration(write_inp, duration):
    file = write_inp(
        f"""[JUNCTIONS]
J1 0 0
[TIMES]
duration {duration}
"""
    )
    model = read_inp_file(file)
    assert model.options.simulation_duration == datetime.timedelta(seconds=7200)


def test_status(write_inp):
    file = write_inp(
        """[JUNCTIONS]
J1 0 0
[PIPES]
P1 J1 J1 100 12 100 0 CLOSED
P2 J1 J1 100 12 100 0 OPEN
P3 J1 J1 100 12 100 0 CV
P4 J1 J1 100 12 100 0
P5 J1 J1 100 12 100 0
P6 J1 J1 100 12 100 0
[VALVES]
V1 J1 J1 100 PRV 1.1 100
V2 J1 J1 100 PRV 1.2 100
V3 J1 J1 100 PRV 1.3 100
V4 J1 J1 100 PRV 1.4 100
V5 J1 J1 100 PRV 1.5 100
V6 J1 J1 100 FCV 88 100
[PUMPS]
PU1 J1 J1 100 12
PU2 J1 J1 100 12
PU3 J1 J1 100 12
PU4 J1 J1 100 12
[STATUS]
P4 CLOSED
P5 CV
PU2 OPEN
PU3 CLOSED
PU4 2.2
V2 OPEN
V3 CLOSED
V4 ACTIVE
V5 999

"""
    )
    model = read_inp_file(file)

    assert model.attributes["PIPES"]["initial_status"] == ("CLOSED", "OPEN", "OPEN", "CLOSED", "OPEN", "OPEN")
    assert model.attributes["PIPES"]["check_valve"] == (False, False, True, False, True, False)
    assert model.attributes["PUMPS"]["initial_status"] == ("OPEN", "OPEN", "CLOSED", "OPEN")
    assert model.attributes["PUMPS"]["base_speed"] == (None, None, None, "2.2")
    assert model.attributes["VALVES"]["valve_status"] == ("ACTIVE", "OPEN", "CLOSED", "ACTIVE", "ACTIVE", "ACTIVE")
    assert model.attributes["VALVES"]["pressure_setting"] == ("1.1", "1.2", "1.3", "1.4", "999", None)
    assert model.attributes["VALVES"]["flow_setting"] == (None, None, None, None, None, "88")


def test_tank_mixing(write_inp):
    file = write_inp(
        """
[TANKS]
;ID   Elev.  InitLvl  MinLvl  MaxLvl  Diam  MinVol  VolCurve  Overflow
;---------------------------------------------------------------------
;Cylindrical tank that can overflow
T1    100     15       5       25     120   0       *          YES

;Non-cylindrical tank with arbitrary diameter
T2   100     15       5       25     1     0

T3   100     15       5       25     1     0
T4   100     15       5       25     1     0
T5   100     15       5       25     1     0

[MIXING]
;Tank      Model
;-----------------------
T2        2COMP     0.2
T3        2COMP
T4        FIFO
T5        LIFO

"""
    )
    model = read_inp_file(file)
    assert tuple(model.attributes["TANKS"]["mixing_model"]) == (None, "2COMP", "2COMP", "FIFO", "LIFO")
    assert tuple(model.attributes["TANKS"]["mixing_fraction"]) == (None, "0.2", None, None, None)
