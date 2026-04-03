from __future__ import annotations

import logging
import os
import platform
from collections.abc import Generator
from contextlib import contextmanager
from ctypes import CDLL, POINTER, c_char_p, c_int, c_long, c_uint64, cdll
from pathlib import Path

from gusnet.i18n import tr

logger = logging.getLogger(__name__)


def setup_types(epalib: CDLL) -> None:
    """Set up argument types for EPANET functions."""
    ph = c_uint64
    epalib.EN_createproject.argtypes = [POINTER(ph)]
    epalib.EN_open.argtypes = [ph, c_char_p, c_char_p, c_char_p]

    epalib.EN_solveH.argtypes = [ph]
    epalib.EN_solveQ.argtypes = [ph]

    epalib.EN_openH.argtypes = [ph]
    epalib.EN_initH.argtypes = [ph, c_int]
    epalib.EN_openQ.argtypes = [ph]
    epalib.EN_initQ.argtypes = [ph, c_int]
    epalib.EN_runH.argtypes = [ph, POINTER(c_long)]
    epalib.EN_runQ.argtypes = [ph, POINTER(c_long)]
    epalib.EN_nextH.argtypes = [ph, POINTER(c_long)]
    epalib.EN_nextQ.argtypes = [ph, POINTER(c_long)]
    epalib.EN_closeH.argtypes = [ph]
    epalib.EN_closeQ.argtypes = [ph]
    epalib.EN_report.argtypes = [ph]
    epalib.EN_deleteproject.argtypes = [ph]
    epalib.EN_geterror.argtypes = [ph, c_char_p, c_int]

    epalib.EN_solveH.errcheck = handle_error
    epalib.EN_solveQ.errcheck = handle_error
    epalib.EN_open.errcheck = handle_error
    epalib.EN_runH.errcheck = handle_error
    epalib.EN_runQ.errcheck = handle_error
    epalib.EN_nextH.errcheck = handle_error
    epalib.EN_nextQ.errcheck = handle_error
    epalib.ENepanet.errcheck = handle_error


def run_analysis(
    inp_file_path: os.PathLike | str, report_file_path: os.PathLike | str, output_file_path: os.PathLike | str
) -> None:
    # from epyt.epanet import epanetapi

    # inp_file_str = str(Path(inp_file_path))
    # report_file_str = str(Path(report_file_path))
    # output_file_str = str(Path(output_file_path))

    # epanet = epanetapi()
    # epanet.ENepanet(inp_file_str, report_file_str, output_file_str)

    # errcode = epanet.errcode

    # if errcode > 0 and errcode < 100:
    #     logger.warning(f"EPANET Warning: {errcode}")
    # elif errcode >= 100:
    #     raise EpanetError(errcode)

    enlib = _get_epanet_cdll()

    inpfile = str(Path(inp_file_path)).encode("utf-8")
    rptfile = str(Path(report_file_path)).encode("utf-8")
    binfile = str(Path(output_file_path)).encode("utf-8")

    # enlib.ENepanet(inpfile, rptfile, binfile, c_void_p())

    with create_project(enlib) as ph:
        enlib.EN_open(ph, inpfile, rptfile, binfile)

        enlib.EN_openH(ph)
        enlib.EN_initH(ph, 1)
        enlib.EN_openQ(ph)
        enlib.EN_initQ(ph, 1)

        t = c_long()
        t_step = c_long()

        while True:
            enlib.EN_runH(ph, t)
            enlib.EN_runQ(ph, t)
            enlib.EN_nextH(ph, t_step)
            enlib.EN_nextQ(ph, t_step)

            if t_step.value <= 0:
                break

        # enlib.EN_saveH(ph)

        enlib.EN_closeH(ph)
        enlib.EN_closeQ(ph)
        enlib.EN_report(ph)
    # enlib.EN_solveH(ph)
    # enlib.EN_solveQ(ph)
    # enlib.EN_report(ph)
    # enlib.EN_savehydfile(ph, binfile)


def _get_epanet_cdll() -> CDLL:
    ops = platform.system().lower()
    if ops in ["windows"]:
        extension = "win"
    elif ops in ["darwin"]:
        extension = "mac"
    else:
        extension = "lnx"

    epanet_path = Path(__file__).parent / "resources" / "epanet" / ("libepanet2." + extension)
    logger.debug(f"Loading EPANET library from path: {epanet_path}")

    if not epanet_path.exists():
        raise EpanetNotFoundError

    enlib = cdll.LoadLibrary(str(epanet_path))

    setup_types(enlib)

    return enlib


@contextmanager
def create_project(enlib) -> Generator[c_uint64, None, None]:
    ph = c_uint64()
    enlib.EN_createproject(ph)

    try:
        yield ph
    finally:
        enlib.EN_deleteproject(ph)


def handle_error(result, func, args):  # noqa: ARG001
    if not result:
        return result

    if result > 100:
        raise EpanetError(result)
    else:
        log_epanet_warning(result)

    return result


def log_epanet_warning(error_code: int) -> None:
    warning_text = get_epanet_error_message(error_code)

    logger.warning(f"EPANET returned warning code {error_code}: {warning_text}")


def get_epanet_error_message(errcode: int) -> str:
    """Get the EPANET error message corresponding to the given error code."""

    err_code_map = {
        # Warnings
        1: tr(
            "System hydraulically unbalanced - convergence to a hydraulic solution was not achieved in the allowed number of trials"  # noqa: E501
        ),
        2: tr(
            "System may be hydraulically unstable - hydraulic convergence was only achieved after the status of all links was held fixed"  # noqa: E501
        ),
        3: tr("System disconnected - one or more nodes with positive demands were disconnected for all supply sources"),
        4: tr(
            "Pumps cannot deliver enough flow or head - one or more pumps were forced to either shut down (due to insufficient head) or operate beyond the maximum rated flow"  # noqa: E501
        ),
        5: tr(
            "Valves cannot deliver enough flow - one or more flow control valves could not deliver the required flow even when fully open"  # noqa: E501
        ),
        6: tr(
            "System has negative pressures - negative pressures occurred at one or more junctions with positive demand"
        ),
        # Runtime errors
        101: tr("insufficient memory available"),
        102: tr("no network data available"),
        103: tr("hydraulics not initialized"),
        104: tr("no hydraulics for water quality analysis"),
        105: tr("water quality not initialized"),
        106: tr("no results saved to report on"),
        107: tr("hydraulics supplied from external file"),
        108: tr("cannot use external file while hydraulics solver is active"),
        109: tr("cannot change time parameter when solver is active"),
        110: tr("cannot solve network hydraulic equations"),
        120: tr("cannot solve water quality transport equations"),
        # Apply only to an input file
        200: tr("one or more errors in input file"),
        201: tr("syntax error"),
        299: tr("invalid section keyword"),
        # Apply to both IO file and API functions
        202: tr("illegal numeric value"),
        203: tr("undefined node"),
        204: tr("undefined link"),
        205: tr("undefined time pattern"),
        206: tr("undefined curve"),
        207: tr("attempt to control a CV/GPV link"),
        208: tr("illegal PDA pressure limits"),
        209: tr("illegal node property value"),
        211: tr("illegal link property value"),
        212: tr("undefined trace node"),
        213: tr("invalid option value"),
        214: tr("too many characters in input line"),
        215: tr("duplicate ID label"),
        216: tr("reference to undefined pump"),
        217: tr("invalid pump energy data"),
        219: tr("illegal valve connection to tank node"),
        220: tr("illegal valve connection to another valve"),
        221: tr("misplaced rule clause in rule-based control"),
        222: tr("link assigned same start and end nodes"),
        # Network consistency
        223: tr("not enough nodes in network"),
        224: tr("no tanks or reservoirs in network"),
        225: tr("invalid lower/upper levels for tank"),
        226: tr("no head curve or power rating for pump"),
        227: tr("invalid head curve for pump"),
        230: tr("nonincreasing x-values for curve"),
        231: tr("no data provided for curve"),
        232: tr("no data provided for pattern"),
        233: tr("network has unconnected nodes"),
        234: tr("network has an unconnected node"),
        # API functions only
        240: tr("nonexistent water quality source"),
        241: tr("nonexistent control"),
        250: tr("invalid format (e.g. too long an ID name)"),
        251: tr("invalid parameter code"),
        252: tr("invalid ID name"),
        253: tr("nonexistent demand category"),
        254: tr("node with no coordinates"),
        255: tr("invalid link vertex"),
        257: tr("nonexistent rule"),
        258: tr("nonexistent rule clause"),
        259: tr("attempt to delete a node that still has links connected to it"),
        260: tr("attempt to delete node assigned as a Trace Node"),
        261: tr("attempt to delete a node or link contained in a control"),
        262: tr("attempt to modify network structure while a solver is open"),
        263: tr("node is not a tank"),
        264: tr("link is not a valve"),
        # File errors
        301: tr("identical file names used for different types of files"),
        302: tr("cannot open input file"),
        303: tr("cannot open report file"),
        304: tr("cannot open binary output file"),
        305: tr("cannot open hydraulics file"),
        306: tr("hydraulics file does not match network data"),
        307: tr("cannot read hydraulics file"),
        308: tr("cannot save results to binary file"),
        309: tr("cannot save results to report file"),
    }

    return err_code_map.get(errcode, tr("Unknown EPANET error code: {code}").format(code=errcode))


class EpanetWrapperError(Exception):
    pass


class EpanetError(EpanetWrapperError):
    """Custom exception for EPANET errors."""

    def __init__(self, errcode: int) -> None:
        self.errcode = errcode

        error_text = get_epanet_error_message(errcode)

        super().__init__(
            tr("Error from EPANET - {errcode} - {error_text}").format(error_text=error_text, errcode=errcode)
        )


class EpanetNotFoundError(EpanetWrapperError):
    def __init__(self):
        super().__init__(tr("Cannot load EPANET library."))


if __name__ == "__main__":
    run_analysis(
        inp_file_path="gusnet/resources/examples/single_pipe_warning.inp",
        report_file_path="rpty.txt",
        output_file_path="outy3.bin",
    )
