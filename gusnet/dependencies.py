from __future__ import annotations

import importlib
import os
import subprocess
import sys
from importlib import invalidate_caches, reload
from pathlib import Path
from typing import Any

from qgis.core import Qgis, QgsApplication, QgsTask

from gusnet.i18n import tr

MESSAGE_CATEGORY = "Gusnet"

# If necessary in future add python version to package directory path
PACKAGE_DIRECTORY = str((Path(__file__).parent / "packages").resolve())
Path(PACKAGE_DIRECTORY).mkdir(parents=True, exist_ok=True)

unpacking_now = False


class CheckAndFetchEpanetTask(QgsTask):
    def __init__(self):
        super().__init__("Check EPANET", QgsTask.Hidden | QgsTask.Silent)

    def run(self) -> bool:
        try:
            check_epanet()
        except ImportError:
            pass
        else:
            return True

        self.setDescription(tr("Fetching EPANET"))

        try:
            fetch_epanet()
        except DependancyInstallError as e:
            if message_log := QgsApplication.messageLog():
                message_log.logMessage(str(e), MESSAGE_CATEGORY, Qgis.MessageLevel.Critical, notifyUser=False)
            return False

        return True


def check_epanet() -> None:
    if "gusnet_epanet" in sys.modules:
        import gusnet_epanet

        importlib.reload(gusnet_epanet)

    import gusnet_epanet  # type: ignore

    if not Path(gusnet_epanet.__file__).exists():
        msg = "File missing - probably due to plugin upgrade"
        raise ImportError(msg)


def fetch_epanet() -> None:
    """Fetches and  unpack gusnet_epanet into the package directory.

    Returns:
        str: The version of WNTR installed.

    Raises:
        WntrInstallError: If WNTR cannot be installed.
    """

    # missing_deps = [package for package in [] if find_spec(package) is None]
    # if len(missing_deps):
    #     raise MissingDependencyError(missing_deps)

    # Try not to let PIP install it twice at same time
    # if unpacking_now:
    #     raise InstallInProgressError
    # unpacking_now = True

    if "python" not in sys.executable.lower():
        if sys.platform == "win32":
            python_bin = str(Path(sys.prefix) / "python.exe")
        else:
            python_bin = "python3"
    else:
        python_bin = sys.executable

    kwargs: dict[str, Any] = {}
    if os.name == "nt":
        kwargs.setdefault("creationflags", subprocess.CREATE_NO_WINDOW)  # type: ignore[attr-defined]

    try:
        process_result = subprocess.run(  # noqa: S603
            [
                python_bin,  # https://github.com/qgis/QGIS/issues/45646
                "-m",
                "pip",
                "install",
                "--quiet",
                "--upgrade",
                "--force-reinstall",
                "--target=" + str(PACKAGE_DIRECTORY),
                "--no-deps",
                # "--find-links=" + cls.wheels_directory(),
                "gusnet_epanet",
            ],
            check=False,
            text=True,
            capture_output=True,
            timeout=60,
            **kwargs,
        )
    except TimeoutError as e:
        msg = tr("Took too long to fetch and install.")
        raise DependancyInstallError(msg) from e
    except FileNotFoundError as e:
        msg = tr("Couldn't find Python")
        raise DependancyInstallError(msg) from e
    finally:
        # unpacking_now = False
        pass

    if process_result.returncode != 0:
        raise DependancyInstallError(process_result.stderr)

    invalidate_caches()

    try:
        import gusnet_epanet  # type: ignore

        reload(gusnet_epanet)

    except ImportError as e:
        raise DependancyInstallError(e) from e


class DependancyInstallError(RuntimeError):
    def __init__(self, exception):
        super().__init__(tr("Couldn't fetch and install gusnet_epanet. {exception}").format(exception=exception))


class MissingDependencyError(DependancyInstallError):
    def __init__(self, missing_deps):
        super().__init__(
            tr("Missing necessary python packages {missing_deps}. Please see help for how to fix this").format(
                missing_deps=(*missing_deps,)
            )
        )


class InstallInProgressError(DependancyInstallError):
    def __init__(self):
        super().__init__(tr("Fetching gusnet_epanet is already in progress. Please wait and try again."))
