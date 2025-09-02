from datetime import datetime, timedelta

import pytest
from qgis.core import (
    QgsDateTimeRange,
    QgsExpression,
    QgsExpressionContext,
    QgsExpressionContextUtils,
    QgsTemporalNavigationObject,
)

import gusnet.expressions  # noqa: F401


def test_curve_ok():
    expr = QgsExpression("gusnet_check_curve('(1,2), (3,4)')")
    assert expr.hasParserError() is False
    assert expr.evaluate() is True
    assert expr.hasEvalError() is False


def test_curve_wrong():
    expr = QgsExpression("gusnet_check_curve('(x,y)')")
    assert expr.hasParserError() is False
    assert expr.evaluate() is False
    assert expr.hasEvalError() is False


@pytest.mark.parametrize("none_value", ["NULL", "''", "'  '"])
def test_curve_null(none_value):
    expr = QgsExpression(f"gusnet_check_curve({none_value})")
    assert expr.hasParserError() is False
    assert expr.evaluate() is None
    assert expr.hasEvalError() is False


def test_pattern_ok():
    expr = QgsExpression("gusnet_check_pattern('1 2 3')")
    assert expr.hasParserError() is False
    assert expr.evaluate() is True
    assert expr.hasEvalError() is False


def test_pattern_wrong():
    expr = QgsExpression("gusnet_check_pattern('x y z')")
    assert expr.hasParserError() is False
    assert expr.evaluate() is False
    assert expr.hasEvalError() is False


@pytest.mark.parametrize("none_value", ["NULL", "''", "'  '"])
def test_pattern_null(none_value):
    expr = QgsExpression(f"gusnet_check_pattern({none_value})")
    assert expr.hasParserError() is False
    assert expr.evaluate() is None
    assert expr.hasEvalError() is False


@pytest.fixture
def expression_context():
    return QgsExpressionContext()


@pytest.fixture
def start_datetime():
    return datetime(2000, 1, 1, 0, 0, 0)


@pytest.fixture
def current_hour():
    return 1


@pytest.fixture
def add_temporal_range(expression_context, start_datetime):
    datetime_range = QgsDateTimeRange(start_datetime, start_datetime + timedelta(hours=24))

    temporal_controller = QgsTemporalNavigationObject()
    temporal_controller.setTemporalExtents(datetime_range)
    expression_context.appendScope(temporal_controller.createExpressionContextScope())


@pytest.fixture
def add_current_hour(expression_context, current_hour, start_datetime, qgis_iface):
    current_time = start_datetime + timedelta(hours=current_hour)
    qgis_iface.mapCanvas().setTemporalRange(QgsDateTimeRange(current_time, current_time + timedelta(hours=1)))
    expression_context.appendScope(QgsExpressionContextUtils.mapSettingsScope(qgis_iface.mapCanvas().mapSettings()))


@pytest.fixture
def expression_context_full(expression_context, add_temporal_range, add_current_hour):
    return expression_context


def test_result_no_context():
    expr = QgsExpression("gusnet_result_at_current_time(array(0, 1, 2))")
    assert expr.hasParserError() is False
    assert expr.evaluate() is None
    assert expr.hasEvalError() is True
    assert expr.evalErrorString() == "Expression context is not set."


def test_result_empty_context():
    expr = QgsExpression("gusnet_result_at_current_time(array(0, 1, 2))")
    assert expr.hasParserError() is False
    assert expr.evaluate(QgsExpressionContext()) == 0.0
    assert expr.hasEvalError() is False


@pytest.mark.parametrize(("current_hour", "expected_value"), [(0, 0.0), (1, 1.0), (2, 2.0)])
def test_result_at_current_time_ok(expression_context_full, expected_value):
    expr = QgsExpression("gusnet_result_at_current_time(array(0,1,2))")
    assert expr.hasParserError() is False
    assert expr.evaluate(expression_context_full) == expected_value
    assert expr.hasEvalError() is False


@pytest.mark.parametrize(("current_hour", "expected_value"), [(1.5, 1.5)])
def test_result_at_current_time_interpolation(expression_context, add_temporal_range, add_current_hour, expected_value):
    expr = QgsExpression("gusnet_result_at_current_time(array(0,1,2))")
    assert expr.hasParserError() is False
    assert expr.evaluate(expression_context) == expected_value
    assert expr.hasEvalError() is False


@pytest.mark.parametrize(("current_hour"), [3.0, 2.1, -1.0, -0.1])
def test_result_too_time_outside_of_scope(expression_context, add_temporal_range, current_hour, add_current_hour):
    expr = QgsExpression("gusnet_result_at_current_time(array(0,1,2))")
    assert expr.hasParserError() is False
    assert expr.evaluate(expression_context) is None
    assert expr.hasEvalError() is True
    assert expr.evalErrorString() == f"Requested time ({current_hour}) is outside of the range of results."


def test_result_single_value(expression_context, add_temporal_range, add_current_hour):
    expr = QgsExpression("gusnet_result_at_current_time(9)")
    assert expr.hasParserError() is False
    assert expr.evaluate(expression_context) == 9
    assert expr.hasEvalError() is False


def test_result_with_no_current_time(expression_context, add_temporal_range):
    expr = QgsExpression("gusnet_result_at_current_time(array(0, 1, 2))")
    assert expr.hasParserError() is False
    assert expr.evaluate(expression_context) == 0.0
    assert expr.hasEvalError() is False


def test_result_with_no_time_range(expression_context, add_current_hour):
    expr = QgsExpression("gusnet_result_at_current_time(array(0, 1, 2))")
    assert expr.hasParserError() is False
    assert expr.evaluate(expression_context) is None
    assert expr.hasEvalError() is True
    assert expr.evalErrorString() == "Animation start time is not set."
