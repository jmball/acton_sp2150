"""Acton SP2150 monochromator control library."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
import logging
import math
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
_NOT_CONNECTED: Final[str] = "Instrument is not connected"

# Protocol and serial framing belong to the device, not to callers.
_FIXED_OPTIONS = frozenset({
    "read_termination", "write_termination", "encoding", "baud_rate",
    "data_bits", "parity", "stop_bits", "flow_control", "end_input", "end_output",
    "resource_pyclass",
})


def _finite_number(value: Number, name: str) -> float:
    """Convert a numeric input, rejecting NaN and infinity."""
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


def _scan_speed_value(speed: Number) -> float:
    """Validate scan speed after rounding to device precision (nm/min)."""
    result = float(f"{_finite_number(speed, 'Scan speed'):.1f}")
    if result <= 0:
        raise ValueError("Scan speed must be positive at the device's one-decimal precision")
    return result


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


class _OperationTimeouts:
    """Configurable operation allowances in ms, shared with the simulator."""

    def __init__(self) -> None:
        # GRATING takes about 20 s; allow additional time for communication.
        self.grating_timeout_ms: float = 30000.0
        # FILTER takes 2.5 s per adjacent position (up to three steps).
        self.filter_timeout_ms: float = 10000.0
        # FHOME has no documented duration; allow a full revolution plus margin.
        self.filter_home_timeout_ms: float = 20000.0
        self.scan_timeout_buffer_ms: float = 5000.0


class sp2150(_OperationTimeouts):
    """Monochromator instrument object."""

    def __init__(self) -> None:
        """Construct object."""
        super().__init__()
        self._instr: MessageBasedResource | None = None

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
            by PyVISA: the instrument resource retains the manager, and this driver
            never closes it.
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

    def disconnect(self) -> None:
        """Close this instrument session; repeated calls are harmless.

        The manager remains open because PyVISA may share it with other callers.
        State is cleared even if closing the instrument raises an exception.
        """
        instr = self._instr
        self._instr = None
        if instr is not None:
            instr.close()

    def _write(self, cmd: str) -> None:
        """Send a command, requiring an active connection."""
        if self._instr is None:
            raise RuntimeError(_NOT_CONNECTED)
        self._instr.write(cmd)

    def _query(self, cmd: str) -> str:
        """Send a command and return the unparsed PyVISA response."""
        if self._instr is None:
            raise RuntimeError(_NOT_CONNECTED)
        return self._instr.query(cmd)

    def _read_bytes(self, count: int) -> bytes:
        """Read bytes, requiring an active connection."""
        if self._instr is None:
            raise RuntimeError(_NOT_CONNECTED)
        return self._instr.read_bytes(count)

    @contextmanager
    def _extended_timeout(self, minimum_ms: float) -> Iterator[None]:
        """Temporarily extend the VISA timeout, preserving a longer caller timeout."""
        instr = self._instr
        if instr is None:
            raise RuntimeError(_NOT_CONNECTED)
        minimum_ms = _finite_number(minimum_ms, "Operation timeout")
        if minimum_ms < 0:
            raise ValueError("Operation timeout must be nonnegative")
        old_timeout = instr.timeout
        if minimum_ms <= old_timeout:
            yield
            return
        instr.timeout = minimum_ms
        try:
            yield
        except BaseException:
            try:
                instr.timeout = old_timeout
            except Exception:
                _LOGGER.warning("Failed to restore the instrument timeout after an error", exc_info=True)
            raise
        else:
            instr.timeout = old_timeout

    def _query_value(self, cmd: str) -> str:
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
        return self._query(cmd)[1:].split(" ")[0]

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
        self._write(cmd)
        terminator = READ_TERMINATION.encode(ENCODING)
        while not resp.endswith(terminator):
            resp += self._read_bytes(1)

        return resp.decode(ENCODING).removesuffix(READ_TERMINATION).strip()

    @property
    def scan_speed(self) -> float:
        """Get grating scan speed in nm/min."""
        return float(self._query_value("?NM/MIN"))

    @scan_speed.setter
    def scan_speed(self, speed: Number) -> None:
        """Set grating scan speed in nm/min.

        Raises
        ------
        ValueError
            Speed is nonfinite or is not positive after rounding to one decimal.
        """
        self._query(f"{_scan_speed_value(speed):.1f} NM/MIN")

    def scan_to_wavelength(self, wavelength: Number) -> None:
        """Scan grating to wavelength in nm.

        Raises
        ------
        ValueError
            Target is nonfinite, or the reported scan speed is nonfinite or
            nonpositive.
        """
        instr = self._instr
        if instr is None:
            raise RuntimeError(_NOT_CONNECTED)
        wavelength = float(f"{_finite_number(wavelength, 'Wavelength'):.1f}")
        buffer_ms = _finite_number(self.scan_timeout_buffer_ms, "Scan timeout buffer")
        if buffer_ms < 0:
            raise ValueError("Scan timeout buffer must be nonnegative")
        # calculate scan time in ms
        current_wavelength = self.wavelength
        speed = _finite_number(self.scan_speed, "Reported scan speed")
        if speed <= 0:
            raise ValueError("Reported scan speed must be positive")
        scan_time = abs(wavelength - current_wavelength) * 60000 / speed

        with self._extended_timeout(scan_time + buffer_ms):
            self._query(f"{wavelength:.1f} NM")

    @property
    def wavelength(self) -> float:
        """Get current grating wavelength position in nm."""
        return float(self._query_value("?NM"))

    @wavelength.setter
    def wavelength(self, wavelength: Number) -> None:
        """Set grating position for wavelength in nm.

        Raises
        ------
        ValueError
            Wavelength is nonfinite.
        """
        self._query(f"{_finite_number(wavelength, 'Wavelength'):.1f} GOTO")

    @property
    def grating(self) -> int:
        """Get grating number."""
        return int(self._query_value("?GRATING"))

    @grating.setter
    def grating(self, grating: Integer) -> None:
        """Set grating number, allowing grating_timeout_ms for indexing."""
        command = f"{int(grating)} GRATING"
        with self._extended_timeout(self.grating_timeout_ms):
            self._query(command)

    @property
    def turret(self) -> int:
        """Get turret number."""
        return int(self._query_value("?TURRET"))

    @turret.setter
    def turret(self, turret: Integer) -> None:
        """Set turrent number."""
        self._query(f"{int(turret)} TURRET")

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
        return int(self._query_value("?FILTER"))

    @filter.setter
    def filter(self, filter_pos: Integer) -> None:
        """Set filter wheel position, allowing filter_timeout_ms for movement."""
        command = f"{int(filter_pos)} FILTER"
        with self._extended_timeout(self.filter_timeout_ms):
            self._query(command)

    def home_filter(self) -> None:
        """Home the filter wheel, allowing filter_home_timeout_ms for movement."""
        with self._extended_timeout(self.filter_home_timeout_ms):
            self._query("FHOME")
