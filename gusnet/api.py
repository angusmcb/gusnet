from __future__ import annotations

import dataclasses
import logging
import pathlib
from typing import TYPE_CHECKING, Literal

from qgis.core import QgsCoordinateReferenceSystem, QgsFeatureSource, QgsProject, QgsVectorLayer

from gusnet import feature_writer
from gusnet.elements import DefaultOptions, FlowUnit, HeadlossFormula, ModelLayer, ResultLayer
from gusnet.feature_reader import read
from gusnet.i18n import tr
from gusnet.interface import WntrModel
from gusnet.style import style
from gusnet.units import SpecificUnitNames
from gusnet.verify_model import verify_model

if TYPE_CHECKING:  # pragma: no cover
    import wntr


logger = logging.getLogger(__name__)


def from_wntr(
    wn: wntr.network.WaterNetworkModel,
    results: wntr.sim.SimulationResults | None = None,
    crs: QgsCoordinateReferenceSystem | str | None = None,
    units: Literal["LPS", "LPM", "MLD", "CMH", "CFS", "GPM", "MGD", "IMGD", "AFD", "CMD"] | None = None,
) -> dict[str, QgsVectorLayer]:
    """Write from WNTR network model to QGIS Layers

    Args:
        wn: the water network model
        results: simulation results, if any.
        crs: The coordinate Reference System of the coordinates in the wntr model. E.g. 'EPSG:4326'.
        units: The flow unit set to use for the created layers.

    """

    network = WntrModel(wn)

    if crs:
        crs_object = QgsCoordinateReferenceSystem(crs)
        if not crs_object.isValid():
            msg = tr("CRS {crs} is not valid.").format(crs=crs)
            raise ValueError(msg)
    else:
        crs_object = QgsCoordinateReferenceSystem()

    if units:
        try:
            flow_unit = FlowUnit[units.upper()]
        except KeyError as e:
            raise FlowUnitError(e) from e

        options = dataclasses.replace(network.options, flow_unit=flow_unit)
        network.options = options

    else:
        logger.warning(
            tr("No units specified. Will use the value from wn: {units_friendly_name}").format(
                units_friendly_name=network.options.flow_unit.friendly_name
            )
        )

    unit_names = SpecificUnitNames.from_options(network.options)

    if results:
        network.set_results(results)

    model_layers: list[ModelLayer | ResultLayer] = list(ResultLayer if results else ModelLayer)

    map_layers: dict[str, QgsVectorLayer] = {}
    for model_layer in model_layers:
        layer_type = "Point" if model_layer.is_node else "LineString"

        layer = QgsVectorLayer(layer_type, model_layer.friendly_name, "memory")
        layer.setCrs(crs_object)
        data_provider = layer.dataProvider()

        gusnet_fields = network.suggested_fields(model_layer)

        attribute_df = (
            network.get_results().get(model_layer)
            if isinstance(model_layer, ResultLayer)
            else network.get_elements().get(model_layer)
        )

        qgs_fields = feature_writer.get_qgs_fields(gusnet_fields, attribute_df, network.options.simulation_duration > 0)

        data_provider.addAttributes(qgs_fields)

        geometries = network.node_geometries if model_layer.is_node else network.link_geometries

        if attribute_df is not None:
            feature_writer.write(data_provider, qgs_fields, attribute_df, geometries)

        layer.updateFields()
        layer.updateExtents()

        style(layer, model_layer, "extended" if results and network.options.simulation_duration else None, unit_names)

        QgsProject.instance().addMapLayer(layer)

        map_layers[model_layer.name] = layer

    return map_layers


def from_inp(
    inp_path: pathlib.Path | str,
    crs: QgsCoordinateReferenceSystem | str | None = None,
) -> dict[str, QgsVectorLayer]:
    """Write from INP file to QGIS Layers

    Args:
        inp_path: path (string or path object) to an input file
        crs: The coordinate Reference System of the coordinates in the inp file.

    """

    network = WntrModel(inp_path)

    return from_wntr(network.wn, crs=crs, units=network.options.flow_unit.name)  # type: ignore[arg-type]


def to_wntr(
    layers: dict[Literal["JUNCTIONS", "RESERVOIRS", "TANKS", "PIPES", "VALVES", "PUMPS"], QgsFeatureSource],
    units: Literal["LPS", "LPM", "MLD", "CMH", "CFS", "GPM", "MGD", "IMGD", "AFD", "CMD"],
    headloss: Literal["H-W", "D-W", "C-M"] | None = None,
    wn: wntr.network.WaterNetworkModel | None = None,
) -> wntr.network.WaterNetworkModel:
    """Read from QGIS layers or feature sources to a WNTR ``WaterNetworkModel``

    Args:
        layers: layers to read from
        units: The flow unit set that the layers being read use.
        headloss: the headloss formula to use
            (H-W for Hazen Williams, D-W for Darcy Weisbach, or C-M for Chezy-Manning).
            Must be set if there is no wn.
            If wn is provided, headloss in wn.options.hydraulic.headloss will be used instead.
        wn: The `WaterNetworkModel` that the layers will be read into. Will create a new model if `None`.

    """

    try:
        model_layers = {ModelLayer(str(layer_name).upper()): layer for layer_name, layer in layers.items()}
    except ValueError as e:
        raise InvalidLayerError(e) from None

    try:
        unit = FlowUnit[units.upper()]
    except KeyError as e:
        raise FlowUnitError(e) from e

    if wn:
        if headloss:
            msg = tr(
                "Cannot set headloss when wn is set. Set the headloss in the wn.options.hydraulic.headloss instead"
            )
            raise ValueError(msg)

        model = WntrModel(wn)
        model.options = dataclasses.replace(model.options, flow_unit=unit)

    else:
        model = WntrModel()

        if not headloss:
            msg = tr("headloss must be set if wn is not set: possible values are: H-W, D-W, C-M")
            raise ValueError(msg)

        headloss_formula = HeadlossFormula(headloss.upper())

        model.options = dataclasses.replace(DefaultOptions(), headloss_formula=headloss_formula, flow_unit=unit)

    all_crs = [layer.sourceCrs().authid() for layer in layers.values() if layer.sourceCrs().isValid()]

    if len(all_crs) == 0:
        logger.warn(tr("No valid CRS found on input layers. Pipe lengths will not be calculated."))

    elif len(all_crs) != len(layers):
        logger.warn(tr("Some input layers do not have a valid CRS. Pipe lengths may not be calculated correctly."))

    if len(set(all_crs)) > 1:
        logger.warn(tr("Multiple different CRSs found on input layers."))

    crs = QgsCoordinateReferenceSystem(all_crs[0]) if all_crs else None

    project = QgsProject.instance()
    transform_context = project.transformContext()
    ellipsoid = project.ellipsoid()

    elements = read(model_layers, crs, transform_context, ellipsoid, model.options.flow_unit)

    verify_model(elements)

    model.set_elements(elements)

    return model.wn


class FlowUnitError(ValueError):
    def __init__(self, exception):
        super().__init__(
            tr("{exception} is not a known set of units. Possible units are: ").format(exception=exception)
            + ", ".join(FlowUnit._member_names_)
        )


class InvalidLayerError(ValueError):
    def __init__(self, value_error: ValueError):
        super().__init__(
            tr(
                "{value_error}. Only acceptable layer types are 'JUNCTIONS', 'RESERVOIRS', 'TANKS', 'PIPES', 'VALVES', 'PUMPS'."  # noqa: E501
            ).format(value_error=value_error)
        )
