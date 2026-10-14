"""Run one monochromator command against hardware or the simulator."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from contextlib import ExitStack
import math

import pyvisa

from sp2150 import sp2150
from virtual_sp2150 import sp2150 as virtual_sp2150


_GETTERS = {
    "get_scan_speed": "scan_speed",
    "get_wavelength": "wavelength",
    "get_grating": "grating",
    "get_turret": "turret",
    "get_grating_info": "grating_info",
    "get_turret_info": "turret_info",
    "get_filter": "filter",
}
_SETTERS = {
    "set_scan_speed": ("scan_speed", float),
    "goto_wavelength": ("wavelength", float),
    "set_grating": ("grating", int),
    "set_turret": ("turret", int),
    "set_filter": ("filter", int),
}


def main(argv: Sequence[str] | None = None) -> int:
    """Validate arguments, run one instrument command, and disconnect.

    Parameters
    ----------
    argv : sequence of str or None, optional
        Command-line arguments without the program name. None uses
        sys.argv[1:].

    Returns
    -------
    exit_code : int
        Zero after successful command execution.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--virtual", action="store_true", help="Use the simulator")
    parser.add_argument("-n", "--resource-name", help="VISA resource name (required for hardware)")
    parser.add_argument("--visa-backend", help="VISA backend, e.g. @py (hardware only)")
    parser.add_argument(
        "function", choices=[*_SETTERS, *_GETTERS, "scan_to_wavelength", "home_filter"],
    )
    parser.add_argument(
        "-p", "--parameter",
        help="Wavelength in nm, speed in nm/min, or an integer grating/turret/filter position",
    )
    parser.add_argument("-t", "--timeout", type=int, default=30000, help="VISA timeout in ms")
    args = parser.parse_args(argv)
    if not args.virtual and not args.resource_name:
        parser.error("--resource-name is required for hardware")
    if args.virtual and args.visa_backend is not None:
        parser.error("--visa-backend is only supported for hardware")
    if args.timeout < 0:
        parser.error("--timeout must be nonnegative")

    parameter: float | int | None = None
    if args.function in _SETTERS or args.function == "scan_to_wavelength":
        if args.parameter is None:
            parser.error(f"{args.function} requires --parameter")
        converter = _SETTERS[args.function][1] if args.function in _SETTERS else float
        try:
            parameter = converter(args.parameter)
        except ValueError:
            parser.error(f"{args.function} requires a valid {converter.__name__} parameter")
        if isinstance(parameter, float) and not math.isfinite(parameter):
            parser.error("--parameter must be finite")
        if args.function == "set_scan_speed" and float(f"{parameter:.1f}") <= 0:
            parser.error("scan speed must be positive at the device's one-decimal precision")
    elif args.parameter is not None:
        parser.error(f"{args.function} does not accept --parameter")

    with ExitStack() as stack:
        manager: pyvisa.ResourceManager | None = None
        device: sp2150 | virtual_sp2150
        if args.virtual:
            device = virtual_sp2150()
        else:
            manager = pyvisa.ResourceManager(args.visa_backend or "")
            stack.callback(manager.close)
            device = sp2150()
        stack.enter_context(device)
        device.connect(args.resource_name or "virtual", resource_manager=manager, timeout=args.timeout)
        if args.function in _GETTERS:
            print(getattr(device, _GETTERS[args.function]))
        elif args.function in _SETTERS:
            setattr(device, _SETTERS[args.function][0], parameter)
        elif args.function == "scan_to_wavelength":
            assert parameter is not None
            device.scan_to_wavelength(parameter)
        else:
            device.home_filter()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
