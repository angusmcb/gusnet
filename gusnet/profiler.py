from __future__ import annotations

import functools
from contextlib import contextmanager

from qgis.core import (
    QgsApplication,
    QgsProcessingException,
    QgsProcessingFeedback,
)

from gusnet.i18n import tr

PROFILER_GROUP_NAME = "Gusnet"


@contextmanager
def profile(name: str, percentage: int | None = None, feedback: QgsProcessingFeedback | None = None):
    """
    Context manager to profile a block of code, optionally within a processing script.
    """

    if feedback and feedback.isCanceled():
        raise QgsProcessingException(tr("Execution of script cancelled by user"))

    if feedback:
        feedback.setProgressText(name)
        # this is to ensure that feedback goes to min 5% straight away rather than waiting at 100
        feedback.setProgress(feedback.progress() + 5)

    qgs_profiler = QgsApplication.profiler()
    if qgs_profiler:
        qgs_profiler.start(name, PROFILER_GROUP_NAME)

    try:
        yield functools.partial(profile, feedback=feedback)

        if feedback and percentage:
            feedback.setProgress(percentage)
    finally:
        if qgs_profiler:
            qgs_profiler.end(PROFILER_GROUP_NAME)
