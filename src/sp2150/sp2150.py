"""Acton SP2150 monochromator control library."""

from __future__ import annotations

import logging
import warnings
from types import TracebackType
from typing import Any, Final

import pyvisa
from pyvisa import constants
from pyvisa.resources import MessageBasedResource, SerialInstrument


_LOGGER = logging.getLogger(__name__)
Number = float | str
Integer = int | str

ENCODING: Final[str] = "ASCII"
WRITE_TERMINATION: Final[str] = "\r"
READ_TERMINATION: Final[str] = " ok\r\n"

# Protocol and serial framing belong to the device, not to callers.
_FIXED_OPTIONS = frozenset({
    "read_termination", "write_termination", "encoding", "baud_rate",
    "data_bits", "parity", "stop_bits", "flow_control", "end_input", "end_output",
    "resource_pyclass",
})


def _discard_fixed_options(options: dict[str, Any]) -> None:
    """Warn and discard overrides, including matching device defaults."""
    fixed = _FIXED_OPTIONS.intersection(options)
    if fixed:
        for name in fixed:
            options.pop(name)
        warnings.warn(
            "Ignoring driver-managed resource options: " + ", ".join(sorted(fixed)),
            UserWarning,
            stacklevel=3,
        )


class sp2150:
    """Monochromator instrument object."""

    def __init__(self) -> None:
        """Construct object."""
        self._instr: MessageBasedResource | None = None
        self._resource_manager: pyvisa.ResourceManager | None = None

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
        try:
            self.disconnect()
        except Exception:
            if exc_type is None:
                raise
            _LOGGER.warning("Failed to disconnect during exception cleanup", exc_info=True)

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
            Resource manager used to create new connection. If `None`, create a new
            resource manager using the default VISA backend. Managers are shared
            by PyVISA: this driver retains the manager but never closes it.
        resource_kwargs : dict
            Options forwarded to PyVISA open_resource for validation and application
            (e.g. timeout in ms, query_delay in seconds, access_mode). Device
            termination, ASCII encoding, serial settings, and resource class
            overrides are discarded with a UserWarning.

        Raises
        ------
        RuntimeError
            Already connected. Disconnect explicitly before reconnecting.
        TypeError
            A resource that is not message-based.

        Notes
        -----
        Serial resources are configured for 9600 baud, 8 data bits, no parity,
        one stop bit, and no flow control. The driver owns only the instrument
        session. Failures after open_resource returns close the session and leave
        this object disconnected. Failures inside open_resource use PyVISA cleanup.
        """
        if self._instr is not None:
            raise RuntimeError("Already connected; disconnect before reconnecting")
        _discard_fixed_options(resource_kwargs)
        if resource_manager is None:
            resource_manager = pyvisa.ResourceManager()
        instr = resource_manager.open_resource(resource_name, **resource_kwargs)
        try:
            if not isinstance(instr, MessageBasedResource):
                raise TypeError("The instrument requires a message-based VISA resource")
            instr.encoding = ENCODING
            instr.write_termination = WRITE_TERMINATION
            instr.read_termination = READ_TERMINATION
            if isinstance(instr, SerialInstrument):
                instr.baud_rate = 9600
                instr.data_bits = 8
                instr.parity = constants.Parity.none
                instr.stop_bits = constants.StopBits.one
                instr.flow_control = constants.ControlFlow.none
                # Stop on the final read-termination byte; writes already append CR.
                instr.end_input = constants.SerialTermination.termination_char
                instr.end_output = constants.SerialTermination.none
            instr.query("NO-ECHO")
        except BaseException:
            try:
                instr.close()
            except Exception:
                _LOGGER.warning("Failed to close the instrument after an error", exc_info=True)
            raise
        self._instr = instr
        self._resource_manager = resource_manager

    def disconnect(self) -> None:
        """Close this instrument session; repeated calls are harmless.

        The manager remains open because PyVISA may share it with other callers.
        State is cleared even if closing the instrument raises an exception.
        """
        instr = self._instr
        self._instr = None
        try:
            if instr is not None:
                instr.close()
        finally:
            self._resource_manager = None

    def _require_connection(self) -> MessageBasedResource:
        """Return the live resource or raise a clear connection-state error."""
        if self._instr is None:
            raise RuntimeError("Instrument is not connected")
        return self._instr

    def _query(self, cmd: str) -> str:
        """Query a command, stripping space at beginning of the response and the unit.

        When echo is disabled, the first character returned is a superfluous space,
        which can be removed.

        Some responses always contain a unit. This is also stripped so properties have
        values with the correct numeric type. The unit of a property can be found in
        its docstring.

        Parameters
        ----------
        cmd : str
            Command to query.

        Returns
        -------
        resp : str
            Response to command with receding space and unit stripped.
        """
        return self._require_connection().query(cmd)[1:].split(" ")[0]

    def _query_manual(self, cmd: str) -> str:
        """Query a command manually looking for the termination character.

        Some commands return partial termination characters, which pyvisa doesn't
        handle properly. This can be circumvented by reading characters one at a
        time and manually checking for the termination character.

        Parameters
        ----------
        cmd : str
            Command to query.

        Returns
        -------
        resp : str
            Response to command with receding space and unit stripped.
        """
        resp = b""
        instr = self._require_connection()
        instr.write(cmd)
        terminator = READ_TERMINATION.encode(ENCODING)
        while not resp.endswith(terminator):
            resp += instr.read_bytes(1)

        return resp.decode(ENCODING).removesuffix(READ_TERMINATION).strip()

    @property
    def scan_speed(self) -> float:
        """Get grating scan speed in nm/min."""
        return float(self._query("?NM/MIN"))

    @scan_speed.setter
    def scan_speed(self, speed: Number) -> None:
        """Set grating scan speed in nm/min."""
        self._require_connection().query(f"{float(speed):.1f} NM/MIN")

    def scan_to_wavelength(self, wavelength: Number) -> None:
        """Scan grating to wavelength in nm."""
        instr = self._require_connection()
        wavelength = float(wavelength)
        # calculate scan time in ms
        scan_time = abs(wavelength - self.wavelength) * 60000 / self.scan_speed

        # if necessary, temporarily increase timeout for a wavelength scan
        old_timeout = instr.timeout
        if long_scan := scan_time > old_timeout:
            # add a few seconds buffer to scan timeout
            instr.timeout = scan_time + 5000

        # run the scan
        try:
            instr.query(f"{wavelength:.1f} NM")
        finally:
            if long_scan:
                instr.timeout = old_timeout

    @property
    def wavelength(self) -> float:
        """Get current grating wavelength position in nm."""
        return float(self._query("?NM"))

    @wavelength.setter
    def wavelength(self, wavelength: Number) -> None:
        """Set grating position for wavelength in nm."""
        self._require_connection().query(f"{float(wavelength):.1f} GOTO")

    @property
    def grating(self) -> int:
        """Get grating number."""
        return int(self._query("?GRATING"))

    @grating.setter
    def grating(self, grating: Integer) -> None:
        """Set grating number."""
        self._require_connection().query(f"{int(grating)} GRATING")

    @property
    def turret(self) -> int:
        """Get turret number."""
        return int(self._query("?TURRET"))

    @turret.setter
    def turret(self, turret: Integer) -> None:
        """Set turrent number."""
        self._require_connection().query(f"{int(turret)} TURRET")

    @property
    def grating_info(self) -> str:
        """Get groove spacing and blaze wavelength of each grating."""
        return self._query_manual("?GRATINGS")

    @property
    def turret_info(self) -> str:
        """Get groove spacing of each grating on each turret."""
        return self._query_manual("?TURRETS")

    @property
    def filter(self) -> int:
        """Get filter wheel position number."""
        return int(self._query("?FILTER"))

    @filter.setter
    def filter(self, filter_pos: Integer) -> None:
        """Set filter wheel position number."""
        self._require_connection().query(f"{int(filter_pos)} FILTER")

    def home_filter(self) -> None:
        """Set filter wheel to home position."""
        self._require_connection().query("FHOME")


if __name__ == "__main__":
    import argparse

    # set up cli
    parser = argparse.ArgumentParser()
    parser.add_argument("-n", "--resource-name", help="Instrument resource name")
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
            "Parameter for function, i.e. wavelength in nm, grating number, turret "
            + "number, filter number"
        ),
    )
    parser.add_argument(
        "-t",
        "--timeout",
        type=int,
        help=("Communications timeout in ms"),
        default=30000,
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
