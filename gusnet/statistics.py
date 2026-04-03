import math
from dataclasses import dataclass

from gusnet.elements import Field, Model, ModelLayer
from gusnet.i18n import tr


@dataclass(frozen=True)
class ModelStatistics:
    """Stores statistics about a model"""

    num_junctions: int
    num_tanks: int
    num_reservoirs: int
    num_pipes: int
    num_valves: int
    num_pumps: int

    pipe_length: str

    pipe_diameters: list[str]

    @classmethod
    def from_model(cls, model: Model) -> "ModelStatistics":
        pipe_length = math.fsum(model.attributes.get(ModelLayer.PIPES, {}).get(Field.LENGTH, []))
        if model.options.flow_unit.is_traditional:
            pipe_length_str = f"{pipe_length:.0f} ft" if pipe_length < 5280 else f"{pipe_length / 5280:.2f} miles"
        else:
            pipe_length_str = f"{pipe_length:.0f} m" if pipe_length < 1000 else f"{pipe_length / 1000:.2f} km"

        return cls(
            num_junctions=len(model.attributes.get(ModelLayer.JUNCTIONS, {}).get(Field.NAME, [])),
            num_tanks=len(model.attributes.get(ModelLayer.TANKS, {}).get(Field.NAME, [])),
            num_reservoirs=len(model.attributes.get(ModelLayer.RESERVOIRS, {}).get(Field.NAME, [])),
            num_pipes=len(model.attributes.get(ModelLayer.PIPES, {}).get(Field.NAME, [])),
            num_valves=len(model.attributes.get(ModelLayer.VALVES, {}).get(Field.NAME, [])),
            num_pumps=len(model.attributes.get(ModelLayer.PUMPS, {}).get(Field.NAME, [])),
            pipe_length=pipe_length_str,
            pipe_diameters=[
                str(d) for d in sorted(set(model.attributes.get(ModelLayer.PIPES, {}).get(Field.DIAMETER, [])))
            ],
        )

    def __str__(self) -> str:
        title = tr("Model Description:")

        counts = [
            f"{ModelLayer.JUNCTIONS.friendly_name}: {self.num_junctions}",
            f"{ModelLayer.TANKS.friendly_name}: {self.num_tanks}",
            f"{ModelLayer.RESERVOIRS.friendly_name}: {self.num_reservoirs}",
            f"{ModelLayer.PIPES.friendly_name}: {self.num_pipes}",
            f"{ModelLayer.VALVES.friendly_name}: {self.num_valves}",
            f"{ModelLayer.PUMPS.friendly_name}: {self.num_pumps}",
        ]

        pipe_data = [
            f"{tr('Total Pipe Length')}: {self.pipe_length}",
            f"{tr('Unique Pipe Diameters')}: {', '.join(self.pipe_diameters)}",
        ]

        return "\n  ".join([title, "", *counts, "", *pipe_data])
