from qgis.core import QgsProcessingProvider
from qgis.PyQt.QtGui import QIcon

from gusnet.gusnet_processing.empty_model import TemplateLayers
from gusnet.gusnet_processing.import_inp import ImportInp
from gusnet.gusnet_processing.run_simulation import ExportInpFile, RunSimulation


class Provider(QgsProcessingProvider):
    def id(self) -> str:
        return "gusnet"

    def name(self) -> str:
        return "Gusnet"

    def icon(self):
        return QIcon("gusnet:logo.svg")

    def loadAlgorithms(self) -> None:  # noqa N802
        self.addAlgorithm(RunSimulation())
        self.addAlgorithm(ImportInp())
        self.addAlgorithm(TemplateLayers())
        self.addAlgorithm(ExportInpFile())
