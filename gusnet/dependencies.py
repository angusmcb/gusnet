from __future__ import annotations

import os
import platform
import subprocess
import sys
from importlib import invalidate_caches, reload
from importlib.util import find_spec
from pathlib import Path
from typing import Any

from gusnet.i18n import tr


class WntrInstaller:
    _unpacking_wntr = False

    @classmethod
    def package_directory(cls):
        major, minor, _ = platform.python_version_tuple()
        packages_path = Path(__file__).parent / "packages" / (major + minor)
        packages_path.mkdir(parents=True, exist_ok=True)
        return str(packages_path.resolve())

    @classmethod
    def install_wntr(cls) -> str:
        """Fetches and installs WNTR.

        Returns:
            str: The version of WNTR installed.

        Raises:
            WntrInstallError: If WNTR cannot be installed.
        """

        missing_deps = [
            package for package in ["pandas", "numpy", "scipy", "networkx", "matplotlib"] if find_spec(package) is None
        ]
        if len(missing_deps):
            raise MissingDependencyError(missing_deps)

        # Try not to let PIP install it twice at same time
        if cls._unpacking_wntr:
            raise InstallInProgressError
        cls._unpacking_wntr = True

        kwargs: dict[str, Any] = {}
        if os.name == "nt":
            kwargs.setdefault("creationflags", subprocess.CREATE_NO_WINDOW)  # type: ignore[attr-defined]

        try:
            process_result = subprocess.run(  # noqa: S603
                [
                    "python" if os.name == "nt" else sys.executable,  # https://github.com/qgis/QGIS/issues/45646
                    "-m",
                    "pip",
                    "install",
                    "--quiet",
                    "--quiet",
                    "--upgrade",
                    "--force-reinstall",
                    "--target=" + cls.package_directory(),
                    "--no-deps",
                    # "--find-links=" + cls.wheels_directory(),
                    "wntr<=1.4",
                ],
                check=False,
                text=True,
                capture_output=True,
                timeout=60,
                **kwargs,
            )
        except TimeoutError as e:
            msg = tr("Took too long to fetch and install.")
            raise WntrInstallError(msg) from e
        except FileNotFoundError as e:
            msg = tr("Couldn't find Python")
            raise WntrInstallError(msg) from e
        finally:
            cls._unpacking_wntr = False

        if process_result.returncode != 0:
            raise WntrInstallError(process_result.stderr)

        invalidate_caches()

        try:
            import wntr  # type: ignore

            reload(wntr)

        except ImportError as e:
            raise WntrInstallError(e) from e

        return wntr.__version__


class WntrInstallError(RuntimeError):
    def __init__(self, exception):
        super().__init__(tr("Couldn't fetch and install WNTR. {exception}").format(exception=exception))


class MissingDependencyError(WntrInstallError):
    def __init__(self, missing_deps):
        super().__init__(
            tr("Missing necessary python packages {missing_deps}. Please see help for how to fix this").format(
                missing_deps=(*missing_deps,)
            )
        )


class InstallInProgressError(WntrInstallError):
    def __init__(self):
        super().__init__(tr("Fetching WNTR is already in progress. Please wait and try again."))
