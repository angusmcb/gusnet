"""
This class contains fixtures and common helper function to keep the test files
shorter.

pytest-qgis (https://pypi.org/project/pytest-qgis) contains the following helpful
fixtures:

* qgis_app initializes and returns fully configured QgsApplication.
  This fixture is called automatically on the start of pytest session.
* qgis_canvas initializes and returns QgsMapCanvas
* qgis_iface returns mocked QgsInterface
* new_project makes sure that all the map layers and configurations are removed.
  This should be used with tests that add stuff to QgsProject.

"""

from pathlib import Path
from unittest.mock import Mock

import pytest
from qgis.core import QgsProject
from qgis.gui import QgsLayerTreeView, QgsMessageBar
from qgis.PyQt.QtGui import QIcon


@pytest.fixture
def qgis_new_project(qgis_new_project):
    QgsProject.instance().clear()


@pytest.fixture(autouse=True, scope="session")
def patch_iface(qgis_app, qgis_iface):
    qgis_iface.statusBarIface = Mock()
    layer_tree_view = QgsLayerTreeView()
    layer_tree_view.currentNode = Mock()
    layer_tree_view.currentNode.return_value = None
    qgis_iface.layerTreeView = lambda: layer_tree_view
    qgis_iface.addToolBarWidget = Mock()
    message_bar = QgsMessageBar()
    qgis_iface.messageBar = lambda: message_bar
    qgis_iface.pluginMenu = Mock()
    qgis_iface.pluginMenu.return_value.actions.return_value = []
    qgis_iface.removePluginMenu = Mock()


@pytest.fixture
def clean_message_bar(qgis_iface):
    qgis_iface.messageBar().clearWidgets()


@pytest.fixture(autouse=True, scope="session")
def processing(qgis_processing):
    import processing

    return processing


# @pytest.fixture(autouse=True, scope="session")
# def check_wntr():
#     from gusnet.dependencies import WntrInstaller

#     try:
#         import wntr
#     except ImportError:
#         WntrInstaller.install_wntr()


@pytest.fixture
def test_inp_dir():
    return Path(__file__).parent / "test_inps"


@pytest.fixture
def bad_inp(test_inp_dir):
    return str(test_inp_dir / "bad_syntax.inp")


@pytest.fixture
def get_example():
    def _(file_name: str):
        return str(Path(__file__).parent.parent / "gusnet" / "resources" / "examples" / file_name)

    return _


@pytest.fixture
def assert_valid_qicon():
    def _(icon: QIcon):
        assert isinstance(icon, QIcon)
        assert not icon.isNull()
        pixmap = icon.pixmap(128)
        assert not pixmap.isNull()

    return _
