__all__ = ["examples", "from_inp", "from_wntr", "from_wntr", "to_wntr"]

import codecs
import configparser
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from qgis.PyQt import QtCore

from gusnet.api import from_inp, from_wntr, to_wntr
from gusnet.dependencies import PACKAGE_DIRECTORY

if TYPE_CHECKING:  # pragma: no cover
    from qgis.gui import QgisInterface


if PACKAGE_DIRECTORY not in sys.path:
    sys.path.append(str(PACKAGE_DIRECTORY))


_cp = configparser.ConfigParser()
with codecs.open(str(Path(__file__).parent / "metadata.txt"), "r", "utf8") as f:
    _cp.read_file(f)
__version__ = _cp.get("general", "version")


def _inp_path(example_name: str) -> str:
    return str(Path(__file__).resolve().parent / "resources" / "examples" / (example_name + ".inp"))


examples = {
    "KY1": _inp_path("ky1"),
    "KY10": _inp_path("ky10"),
    "VALVES": _inp_path("valves"),
}


QtCore.QDir.addSearchPath("gusnet", str(Path(__file__).resolve().parent / "resources" / "icons"))


def classFactory(iface: "QgisInterface"):  # noqa N802
    from gusnet.plugin import Plugin

    return Plugin()
