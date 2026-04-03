import math
from dataclasses import dataclass

from gusnet.elements import Field, Model, ModelLayer


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
        if model.options.flow_units.is_traditional:
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
        return f"""Model Description:
        Junctions: {self.num_junctions}
        Tanks: {self.num_tanks}
        Reservoirs: {self.num_reservoirs}
        Pipes: {self.num_pipes}
        Valves: {self.num_valves}
        Pumps: {self.num_pumps}

        Total Pipe Length: {self.pipe_length}
        Unique Pipe Diameters: {", ".join(self.pipe_diameters)}
        """
