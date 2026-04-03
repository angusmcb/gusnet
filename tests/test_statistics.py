from gusnet.elements import DEFAULT_OPTIONS, Field, Model, ModelLayer
from gusnet.network import Network
from gusnet.statistics import ModelStatistics


def test_model_statistics():
    model_atts = {
        ModelLayer.JUNCTIONS: {Field.NAME: [f"J{i}" for i in range(10)]},
        ModelLayer.TANKS: {Field.NAME: [f"T{i}" for i in range(2)]},
        ModelLayer.RESERVOIRS: {Field.NAME: [f"R{i}" for i in range(1)]},
        ModelLayer.PIPES: {
            Field.NAME: [f"P{i}" for i in range(15)],
            Field.LENGTH: [100] * 15,
            Field.DIAMETER: [12] * 10 + [24] * 5,
        },
        ModelLayer.VALVES: {Field.NAME: [f"V{i}" for i in range(3)]},
        ModelLayer.PUMPS: {Field.NAME: [f"PU{i}" for i in range(4)]},
    }

    model = Model(Network(), DEFAULT_OPTIONS, model_atts)

    stats = ModelStatistics.from_model(model)

    assert stats.num_junctions == 10
    assert stats.num_tanks == 2
    assert stats.num_reservoirs == 1
    assert stats.num_pipes == 15
    assert stats.num_valves == 3
    assert stats.num_pumps == 4
    assert stats.pipe_length == "1.50 km"
    assert stats.pipe_diameters == ["12", "24"]

    expected_str = """Model Description:

  Junctions: 10
  Tanks: 2
  Reservoirs: 1
  Pipes: 15
  Valves: 3
  Pumps: 4

  Total Pipe Length: 1.50 km
  Unique Pipe Diameters: 12, 24"""

    assert str(stats) == expected_str
