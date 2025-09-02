from __future__ import annotations

from typing import Any, Literal

from qgis.core import (
    Qgis,
    QgsAbstractVectorLayerLabeling,
    QgsClassificationPrettyBreaks,
    QgsDefaultValue,
    QgsEditorWidgetSetup,
    QgsFeatureRenderer,
    QgsField,
    QgsGraduatedSymbolRenderer,
    QgsLineSymbol,
    QgsMarkerLineSymbolLayer,
    QgsMarkerSymbol,
    QgsPalLayerSettings,
    QgsProperty,
    QgsSimpleLineSymbolLayer,
    QgsSimpleMarkerSymbolLayer,
    QgsSingleSymbolRenderer,
    QgsStyle,
    QgsSymbol,
    QgsVectorLayer,
    QgsVectorLayerSimpleLabeling,
    QgsVectorLayerTemporalProperties,
)

from gusnet.elements import (
    Field,
    FieldGroup,
    MapFieldType,
    ModelLayer,
    Parameter,
    ResultLayer,
    SimpleFieldType,
)
from gusnet.i18n import tr
from gusnet.units import SpecificUnitNames, UnitNames


def style(
    layer: QgsVectorLayer,
    layer_type: ModelLayer | ResultLayer,
    theme: Literal["extended"] | None = None,
    units: UnitNames | None = None,
):
    if not units:
        units = UnitNames()

    styler = _LayerStyler(layer, layer_type, theme, units)

    layer.setRenderer(styler.layer_renderer)
    layer.setLabeling(styler.labeling)
    styler.setup_extended_period()

    qgs_field: QgsField
    for i, qgs_field in enumerate(layer.fields()):
        try:
            field = Field(qgs_field.name().lower())
        except ValueError:
            continue

        field_styler = _FieldStyler(field, theme, units)

        layer.setFieldAlias(i, field_styler.alias)
        layer.setEditorWidgetSetup(i, field_styler.editor_widget)
        layer.setDefaultValueDefinition(i, field_styler.default_value)
        layer.setConstraintExpression(i, *field_styler.constraint)


class _FieldStyler:
    def __init__(self, field_type: Field, theme: str | None, units: UnitNames) -> None:
        self.field = field_type
        self.theme = theme
        self.units = units

    @property
    def editor_widget(self) -> QgsEditorWidgetSetup:
        # [(f.editorWidgetSetup().type(), f.editorWidgetSetup().config()) for f in iface.activeLayer().fields()]

        if isinstance(self.field.type, Parameter):
            if self.theme != "extended":
                config: dict[str, Any] = {"Style": "SpinBox", "Precision": 2}

                config["Suffix"] = "  " + self.units.get(self.field.type)

                if self.field.field_group & FieldGroup.REQUIRED:
                    config["AllowNull"] = False

                return QgsEditorWidgetSetup("Range", config)
            else:
                return QgsEditorWidgetSetup("List", {})

        if self.field.type is SimpleFieldType.BOOL:
            return QgsEditorWidgetSetup("CheckBox", {"AllowNullState": False})

        if self.field.type in MapFieldType:
            value_map = [{enum_instance.friendly_name: enum_instance.value} for enum_instance in self.field.type.value]

            return QgsEditorWidgetSetup("ValueMap", {"map": value_map})

        if self.field.type in [SimpleFieldType.STR, SimpleFieldType.PATTERN, SimpleFieldType.CURVE]:
            return QgsEditorWidgetSetup("TextEdit", {"IsMultiline": False, "UseHtml": False})

        raise KeyError  # pragma: no cover

    @property
    def default_value(self) -> QgsDefaultValue:
        # [f.defaultValueDefinition() for f in iface.activeLayer().fields()]

        if self.field is Field.ROUGHNESS:
            return QgsDefaultValue("100")  # TODO: check if it is d-w or h-w

        if self.field is Field.DIAMETER:
            return QgsDefaultValue("100")  # TODO: check if it is lps or gpm...

        if self.field in [Field.MINOR_LOSS, Field.PRESSURE_SETTING]:
            return QgsDefaultValue("0.0")

        if self.field is Field.BASE_SPEED:
            return QgsDefaultValue("1.0")

        if self.field is Field.POWER:
            return QgsDefaultValue("50.0")

        if self.field.type in MapFieldType:
            return QgsDefaultValue(f"'{next(iter(self.field.type.value)).value}'")

        if self.field.type in [SimpleFieldType.STR, SimpleFieldType.PATTERN, SimpleFieldType.CURVE]:
            return QgsDefaultValue("''")  # because 'NULL' doesn't look nice

        return QgsDefaultValue()

    @property
    def alias(self) -> str:
        if isinstance(self.units, SpecificUnitNames) and isinstance(self.field.type, Parameter):
            return tr("{field} ({unit})").format(field=self.field.friendly_name, unit=self.units.get(self.field.type))

        return self.field.friendly_name

    @property
    def constraint(self) -> tuple[str, str] | tuple[None, None]:
        """Returns field constraint. Either:
        tuple of constraint expression and description for the field
        None, None if no constraint is needed.
        """

        if self.field is Field.NAME:
            return (
                "name IS NULL OR (length(name) < 32 AND name NOT LIKE '% %')",
                tr("Name must either be blank for automatic naming, or a string of up to 31 characters with no spaces"),
            )
        if self.field is Field.DIAMETER:
            return "diameter > 0", tr("Diameter must be greater than 0")
        if self.field is Field.ROUGHNESS:
            return "roughness > 0", tr("Roughness must be greater than 0")
        if self.field is Field.LENGTH:
            return "length is NULL  OR  length > 0", tr(
                "Length must be empty/NULL (will be calculated) or greater than 0"
            )

        if self.field is Field.MINOR_LOSS:
            return "minor_loss >= 0", tr("Minor loss must be greater than or equal to 0")
        if self.field is Field.BASE_SPEED:
            return "base_speed > 0", tr("Base speed must be greater than 0")
        if self.field is Field.POWER:
            return "if( upper(pump_type) is 'POWER', power > 0, true)", tr(
                "Power pumps must have a power greater than 0"
            )

        if self.field.type is SimpleFieldType.PATTERN:
            return (
                f"gusnet_check_pattern({self.field.value}) IS NOT false",
                tr("Patterns must be a string of numbers separated by spaces"),
            )

        curve_message = tr("Curves must be a list of tuples, e.g. (1,2), (3,4)")

        if self.field is Field.PUMP_CURVE:
            return (
                "if( upper(pump_type) is 'HEAD', gusnet_check_curve(pump_curve) IS true, true) ",
                tr("Head pumps must have a pump curve. {curve_description}").format(
                    curve_description=curve_message,
                ),
            )

        if self.field is Field.HEADLOSS_CURVE:
            return (
                "if( upper(valve_type) is 'GPV', gusnet_check_curve(headloss_curve) IS true, true) ",
                tr("General Purpose Valves must have a headloss curve. {curve_description}").format(
                    curve_description=curve_message,
                ),
            )

        if self.field.type is SimpleFieldType.CURVE:
            return (f"gusnet_check_curve({self.field.value}) IS NOT false", curve_message)

        return None, None


class _LayerStyler:
    def __init__(
        self, layer: QgsVectorLayer, layer_type: ModelLayer | ResultLayer, theme: str | None, units: UnitNames
    ):
        self.layer = layer
        self.layer_type = layer_type
        self.theme = theme
        self.units = units

    def setup_extended_period(self) -> None:
        if isinstance(self.layer_type, ResultLayer) and self.theme == "extended":
            temporal_properties: QgsVectorLayerTemporalProperties = self.layer.temporalProperties()
            temporal_properties.setIsActive(True)
            temporal_properties.setMode(Qgis.VectorTemporalMode.RedrawLayerOnly)

    @property
    def labeling(self) -> QgsAbstractVectorLayerLabeling | None:
        if self.layer_type is ResultLayer.LINKS:
            label_settings = QgsPalLayerSettings()
            label_settings.drawLabels = False
            label_settings.fieldName = "flowrate"
            label_settings.decimals = 1
            label_settings.formatNumbers = True
            return QgsVectorLayerSimpleLabeling(label_settings)

        return None

    @property
    def layer_renderer(self) -> QgsFeatureRenderer:
        if isinstance(self.layer_type, ModelLayer):
            return QgsSingleSymbolRenderer(self._symbol)

        field = Field.PRESSURE if self.layer_type is ResultLayer.NODES else Field.VELOCITY

        field_name = field.name
        attribute_expression = (
            f'gusnet_result_at_current_time("{field_name}")' if self.theme == "extended" else field_name
        )
        unit_name = ""
        if isinstance(field.type, Parameter):
            unit_name = self.units.get(field.type)

        renderer = QgsGraduatedSymbolRenderer()
        renderer.setClassAttribute(attribute_expression)
        renderer.setSourceSymbol(self._symbol)
        classification_method = QgsClassificationPrettyBreaks()
        classification_method.setLabelPrecision(1)
        # classification_method.setLabelTrimTrailingZeroes(False)
        classification_method.setLabelFormat("%1 - %2 " + unit_name)
        renderer.setClassificationMethod(classification_method)

        renderer.updateClasses(self.layer, 5)

        color_ramp = QgsStyle().defaultStyle().colorRamp("Spectral")
        color_ramp.invert()
        renderer.updateColorRamp(color_ramp)

        return renderer

    @property
    def _symbol(self) -> QgsSymbol:
        if self.layer_type is ModelLayer.JUNCTIONS:
            return QgsMarkerSymbol.createSimple(CIRCLE | WHITE_FILL | HAIRLINE_STROKE | JUNCTION_SIZE)

        if self.layer_type is ModelLayer.TANKS:
            return QgsMarkerSymbol.createSimple(SQUARE | WHITE_FILL | HAIRLINE_STROKE | TANK_SIZE)

        if self.layer_type is ModelLayer.RESERVOIRS:
            return QgsMarkerSymbol.createSimple(TRAPEZOID | WHITE_FILL | HAIRLINE_STROKE | RESERVOIR_SIZE)

        if self.layer_type is ModelLayer.PIPES:
            return QgsLineSymbol.createSimple(MEDIUM_LINE | TRIM_ENDS)

        background_line = QgsSimpleLineSymbolLayer.create(HAIRWIDTH_LINE | GREY_LINE | DOTTY_LINE)

        if self.layer_type is ModelLayer.VALVES:
            left_triangle = QgsSimpleMarkerSymbolLayer.create(TRIANGLE | BLACK_FILL | NO_STROKE)
            right_triangle = QgsSimpleMarkerSymbolLayer.create(TRIANGLE | BLACK_FILL | NO_STROKE | ROTATE_180)
            # creating using nomral __init__ with list crashes 3.34
            valve_marker = QgsMarkerSymbol.createSimple(left_triangle.properties())  # left_triangle, right_triangle])
            valve_marker.appendSymbolLayer(right_triangle)
            return _line_with_marker(background_line, valve_marker)

        if self.layer_type is ModelLayer.PUMPS:
            pump_body = QgsSimpleMarkerSymbolLayer.create(CIRCLE | PUMP_SIZE | BLACK_FILL | NO_STROKE)
            pump_outlet = QgsSimpleMarkerSymbolLayer.create(OUTLET_SQUARE | PUMP_SIZE | BLACK_FILL | NO_STROKE)
            pump_marker = QgsMarkerSymbol.createSimple(pump_body.properties())
            pump_marker.appendSymbolLayer(pump_outlet)
            return _line_with_marker(background_line, pump_marker)

        if self.layer_type is ResultLayer.NODES:
            return QgsMarkerSymbol.createSimple(CIRCLE | NO_STROKE | NODE_SIZE)

        if self.layer_type is ResultLayer.LINKS:
            line = QgsSimpleLineSymbolLayer.create(THICK_LINE)
            arrow = QgsMarkerSymbol.createSimple(ARROW | THICK_STROKE)

            flowrate_field = "gusnet_result_at_current_time( flowrate )" if self.theme == "extended" else "flowrate"

            exp = QgsProperty.fromExpression(f"if( {flowrate_field} <0,180,0)")
            arrow.setDataDefinedAngle(exp)
            return _line_with_marker(line, arrow)

        raise KeyError  # pragma: no cover


def _line_with_marker(background_line: QgsLineSymbol, marker: QgsMarkerSymbol) -> QgsLineSymbol:
    marker_line = QgsMarkerLineSymbolLayer.create(CENTRAL_PLACEMENT)
    marker_line.setSubSymbol(marker)
    combined_symbol = QgsLineSymbol.createSimple(background_line.properties())
    combined_symbol.appendSymbolLayer(marker_line)
    return combined_symbol


# USE THE FOLLOWING TO DISCOVER WHAT PROPERTIES ARE AVAILABLE:
# iface.activeLayer().renderer().symbol().symbolLayers()[0].properties()
# iface.activeLayer().renderer().symbol().symbolLayers()[0].subSymbol().symbolLayers()[0].properties()

CIRCLE = {"name": "circle"}
SQUARE = {"name": "square", "joinstyle": "miter"}
TRAPEZOID = {"name": "trapezoid", "angle": "180", "joinstyle": "miter"}
TRIANGLE = {"name": "filled_arrowhead"}
ARROW = {"name": "arrowhead", "offset": "0.5,0", "size": "2.0"}
OUTLET_SQUARE = {"name": "half_square", "vertical_anchor_point": "2", "angle": "90"}
WHITE_FILL = {"color": "white"}
BLACK_FILL = {"color": "black"}
HAIRLINE_STROKE = {"outline_color": "black", "outline_style": "solid", "outline_width": "0"}
THICK_STROKE = {"outline_width": "0.6"}
NO_STROKE = {"outline_style": "no"}
JUNCTION_SIZE = {"size": "1.8"}
NODE_SIZE = {"size": "2.0"}
TANK_SIZE = {"size": "2.5"}
RESERVOIR_SIZE = {"size": "5"}
VALVE_SIZE = {"size": "3"}
PUMP_SIZE = {"size": "2"}
HAIRWIDTH_LINE = {"line_width": "0"}
MEDIUM_LINE = {"line_width": "0.4"}
THICK_LINE = {"line_width": "0.6"}
TRIM_ENDS = {"trim_distance_end": "0.9", "trim_distance_start": "0.9"}
DOTTY_LINE = {"line_style": "dot"}
GREY_LINE = {"line_color": "35,35,35,255,rgb:0.13725490196078433,0.13725490196078433,0.13725490196078433,1"}
ROTATE_180 = {"angle": "180"}
CENTRAL_PLACEMENT = {"placements": "CentralPoint"}
