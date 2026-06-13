from __future__ import annotations

import ast
import dataclasses
import datetime
import logging
import typing
from enum import Enum

from qgis.core import QgsExpressionContextUtils, QgsProject

from gusnet.elements import DEFAULT_OPTIONS, ModelOptions
from gusnet.pattern_curve import Pattern

logger = logging.getLogger(__name__)

LEGACY_OPTION_NAMES = {
    "flow_units": "flow_unit",
    "demand_type": "demand_model",
    "energy_pattern": "energy_price_pattern",
    "mass_unit": "mass_units",
}
_SETTING_PREFIX = "gusnet_"
_LAYERS_KEY = "model_layers"


def saved_layers(project: QgsProject | None = None) -> dict[str, str]:
    project = project or QgsProject.instance()

    str_value = QgsExpressionContextUtils.projectScope(project).variable(_SETTING_PREFIX + _LAYERS_KEY)

    if not str_value:
        return {}

    try:
        output = ast.literal_eval(str_value)
    except (ValueError, SyntaxError):
        return {}

    if isinstance(output, dict):
        return output
    else:
        return {}


def save_layers(layers: dict) -> None:
    QgsExpressionContextUtils.setProjectVariable(QgsProject.instance(), _SETTING_PREFIX + _LAYERS_KEY, str(layers))


def saved_options(project: QgsProject | None = None) -> ModelOptions:
    """Get saved water network options"""
    if not project:
        project = QgsProject.instance()

    data = {}

    expression_context = QgsExpressionContextUtils.projectScope(project)
    if not expression_context:
        raise RuntimeError

    option_types = typing.get_type_hints(ModelOptions)

    for field in dataclasses.fields(ModelOptions):
        value = expression_context.variable(_SETTING_PREFIX + field.name)

        if value is None:
            if field.name in LEGACY_OPTION_NAMES:
                legacy_name = LEGACY_OPTION_NAMES[field.name]
                value = expression_context.variable(_SETTING_PREFIX + legacy_name)

            if value is None:
                continue

        required_type = option_types[field.name]

        try:
            if issubclass(required_type, datetime.timedelta):
                value = float(value)
                value = datetime.timedelta(hours=value)
            else:
                value = required_type(value)
        except (ValueError, TypeError):
            value = DEFAULT_OPTIONS.__getattribute__(field.name)
            logger.warning(f"Could not read setting for {field.name}, using default value {value}")

        data[field.name] = value

    return dataclasses.replace(DEFAULT_OPTIONS, **data)


def save_options(options: ModelOptions) -> None:
    """Save water network model options"""

    for field in dataclasses.fields(ModelOptions):
        value = getattr(options, field.name)

        if isinstance(value, Enum):
            value = value.value

        if isinstance(value, Pattern):
            value = str(value)

        if isinstance(value, datetime.timedelta):
            value = value.total_seconds() / 3600.0  # store as hours

        QgsExpressionContextUtils.setProjectVariable(QgsProject.instance(), _SETTING_PREFIX + field.name, value)
