"""Acton SP2150 monochromator control library."""

from __future__ import annotations

from types import TracebackType
from typing import Any

import pyvisa
from sp2150.sp2150 import Integer, Number, _validate_fixed_options


class sp2150:
    """Monochromator instrument object."""

    def __init__(self) -> None:
        """Initialise with dummy parameters."""
        self._scan_speed = 1000.0
        self._wavelength = 0.0
        self._grating = 1
        self._turret = 1
        self._grating_info = "dummy info"
        self._turret_info = "dummy info"
        self._filter = 1

        self._write_termination = "\r"
        self._read_termination = " ok\r\n"
        self.instr: None = None
        self._connected = False

    def __enter__(self) -> sp2150:
        """Enter the runtime context related to this object."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Exit the runtime context related to this object."""
        self.disconnect()

    def connect(
        self,
        resource_name: str,
        *,
        resource_manager: pyvisa.ResourceManager | None = None,
        **resource_kwargs: Any,
    ) -> None:
        """Connect to the instrument.

        Parameters
        ----------
        resource_name : str
            Full VISA resource name, e.g. "ASRL2::INSTR", "GPIB0::14::INSTR" etc. See
            https://pyvisa.readthedocs.io/en/latest/introduction/names.html for more
            info on correct formatting for resource names.
        resource_manager : pyvisa.ResourceManager, optional
            Accepted for API compatibility. Never used or closed by the simulator.
        resource_kwargs : dict
            Accepted and ignored without contacting a VISA backend. Fixed device
            settings and resource class overrides are rejected like the driver;
            other options are not validated by the simulator.
        """
        if self._connected:
            raise RuntimeError("Already connected; disconnect before reconnecting")
        _validate_fixed_options(resource_kwargs)
        self._connected = True

    def disconnect(self) -> None:
        """Disconnect instrument."""
        self._connected = False

    def _query(self, cmd: str) -> None:
        """Placeholder: the simulator does not emulate VISA commands."""
        pass

    def _require_connection(self) -> None:
        """Require the same connection state as the hardware driver."""
        if not self._connected:
            raise RuntimeError("Instrument is not connected")

    @property
    def scan_speed(self) -> float:
        """Get grating scan speed in nm/min."""
        self._require_connection()
        return self._scan_speed

    @scan_speed.setter
    def scan_speed(self, speed: Number) -> None:
        """Set grating scan speed in nm/min."""
        self._require_connection()
        self._scan_speed = float(f"{float(speed):.1f}")

    def scan_to_wavelength(self, wavelength: Number) -> None:
        """Scan grating to wavelength in nm."""
        self.wavelength = wavelength

    @property
    def wavelength(self) -> float:
        """Get current grating wavelength position in nm."""
        self._require_connection()
        return self._wavelength

    @wavelength.setter
    def wavelength(self, wavelength: Number) -> None:
        """Set grating position for wavelength in nm."""
        self._require_connection()
        self._wavelength = float(f"{float(wavelength):.1f}")

    @property
    def grating(self) -> int:
        """Get grating number."""
        self._require_connection()
        return self._grating

    @grating.setter
    def grating(self, grating: Integer) -> None:
        """Set grating number."""
        self._require_connection()
        self._grating = int(grating)

    @property
    def turret(self) -> int:
        """Get turret number."""
        self._require_connection()
        return self._turret

    @turret.setter
    def turret(self, turret: Integer) -> None:
        """Set turrent number."""
        self._require_connection()
        self._turret = int(turret)

    @property
    def grating_info(self) -> str:
        """Get groove spacing and blaze wavelength of each grating."""
        self._require_connection()
        return self._grating_info

    @property
    def turret_info(self) -> str:
        """Get groove spacing of each grating on each turret."""
        self._require_connection()
        return self._turret_info

    @property
    def filter(self) -> int:
        """Get filter wheel position number."""
        self._require_connection()
        return self._filter

    @filter.setter
    def filter(self, filter_pos: Integer) -> None:
        """Set filter wheel position number."""
        self._require_connection()
        self._filter = int(filter_pos)

    def home_filter(self) -> None:
        """Set filter wheel to home position."""
        self._require_connection()
        self._filter = 1


if __name__ == "__main__":
    import argparse

    # set up cli
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-n", "--resource-name", default="virtual", help="Instrument resource name"
    )
    parser.add_argument(
        "function",
        help="function to call",
        choices=[
            "set_scan_speed",
            "get_scan_speed",
            "scan_to_wavelength",
            "goto_wavelength",
            "get_wavelength",
            "set_grating",
            "get_grating",
            "set_turret",
            "get_turret",
            "get_grating_info",
            "get_turret_info",
            "set_filter",
            "get_filter",
            "home_filter",
        ],
    )
    parser.add_argument(
        "-p",
        "--parameter",
        help=(
            "parameter for function, i.e. wavelength in nm, grating number, turret "
            + "number, filter number"
        ),
    )
    parser.add_argument(
        "-t", "--timeout", type=int, default=30000,
        help="Communications timeout in ms (accepted for API compatibility)",
    )
    args = parser.parse_args()

    # run command in context manager to ensure proper cleanup
    with sp2150() as mono:
        mono.connect(args.resource_name, timeout=args.timeout)

        # call function
        if args.function == "set_scan_speed":
            mono.scan_speed = args.parameter
        elif args.function == "get_scan_speed":
            print(mono.scan_speed)
        elif args.function == "scan_to_wavelength":
            mono.scan_to_wavelength(args.parameter)
        elif args.function == "goto_wavelength":
            mono.wavelength = args.parameter
        elif args.function == "get_wavelength":
            print(mono.wavelength)
        elif args.function == "set_grating":
            mono.grating = args.parameter
        elif args.function == "get_grating":
            print(mono.grating)
        elif args.function == "set_turret":
            mono.turret = args.parameter
        elif args.function == "get_turret":
            print(mono.turret)
        elif args.function == "get_grating_info":
            print(mono.grating_info)
        elif args.function == "get_turret_info":
            print(mono.turret_info)
        elif args.function == "set_filter":
            mono.filter = args.parameter
        elif args.function == "get_filter":
            print(mono.filter)
        elif args.function == "home_filter":
            mono.home_filter()
