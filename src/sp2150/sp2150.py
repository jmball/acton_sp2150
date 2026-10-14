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


def _to_finite_float(value: Number) -> float:
    """Convert a numeric input, rejecting NaN and infinity.

    Parameters
    ----------
    value : float or str
        Value to convert to a finite float.

    Returns
    -------
    result : float
        The converted finite value.
    """
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("Value must be finite")
    return result


def _discard_fixed_options(options: dict[str, Any]) -> None:
    """Warn and remove caller overrides of fixed device settings.

    Parameters
    ----------
    options : dict of str to object
        Resource options to modify in place. Fixed settings are removed
        even when supplied values match the device defaults.
    """
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
    """Control an Acton SP-2150 monochromator and FA-2448 filter wheel.

    Connect before using instrument commands. Operation allowances extend
    the resource timeout when needed and restore it afterward. A longer
    or infinite caller timeout is preserved.
    Numeric command inputs are validated before checking connection state.

    Attributes
    ----------
    grating_timeout_ms : float
        Minimum grating-selection timeout in ms. Default is 30000.
    filter_timeout_ms : float
        Minimum filter-selection timeout in ms. Default is 10000.
    filter_home_timeout_ms : float
        Minimum filter-homing timeout in ms. Default is 20000.
    scan_timeout_buffer_ms : float
        Buffer added to the estimated scan duration in ms. Default is 5000.
    """

    def __init__(self) -> None:
        """Create a disconnected instrument with default timeouts."""
        # GRATING takes about 20 s; allow additional time for communication.
        self.grating_timeout_ms: float = 30000.0
        # FILTER takes 2.5 s per adjacent position (up to three steps).
        self.filter_timeout_ms: float = 10000.0
        # FHOME has no documented duration; allow a full revolution plus margin.
        self.filter_home_timeout_ms: float = 20000.0
        self.scan_timeout_buffer_ms: float = 5000.0
        self._instr: MessageBasedResource | None = None

    def __enter__(self) -> sp2150:
        """Return this instance for use as a context manager.

        Returns
        -------
        self : sp2150
            This instrument instance; entering the context does not connect it.
        """
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Disconnect when leaving the context.

        If the context body failed, preserve its exception and log any
        additional disconnection failure.

        Parameters
        ----------
        exc_type : type or None
            Exception type from the context body, or None on normal exit.
        exc_value : BaseException or None
            Exception from the context body, or None on normal exit.
        traceback : types.TracebackType or None
            Traceback from the context body, or None on normal exit.
        """
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
        """Connect to a message-based VISA instrument.

        Disconnect before reconnecting. The driver fixes ASCII encoding and
        termination strings; RS232 uses 9600 baud, 8 data bits, no parity, one
        stop bit, and no flow control.

        If configuration or initialization fails after opening the resource,
        close the session and leave this instance disconnected. Failures
        inside PyVISA open_resource are handled by PyVISA.

        Parameters
        ----------
        resource_name : str
            VISA resource name or alias, such as "ASRL2::INSTR" or
            "GPIB0::14::INSTR".
        resource_manager : pyvisa.ResourceManager or None, optional
            Manager used to open the resource. None selects the default VISA
            backend. The driver closes only its instrument session; the
            PyVISA resource retains the manager.
        **resource_kwargs
            Options forwarded to PyVISA open_resource, such as timeout in ms,
            query_delay in seconds, or access_mode. Overrides of fixed device
            settings and resource class selection warn and are ignored.
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

        The resource manager remains open because PyVISA may share it with
        other callers. Connection state is cleared even if closing fails.
        """
        instr = self._instr
        self._instr = None
        if instr is not None:
            instr.close()

    def _write(self, cmd: str) -> None:
        """Send a command over the active connection.

        Parameters
        ----------
        cmd : str
            Device command without its write termination.
        """
        if self._instr is None:
            raise RuntimeError(_NOT_CONNECTED)
        self._instr.write(cmd)

    def _query(self, cmd: str) -> str:
        """Send a command and read its response over the active connection.

        Parameters
        ----------
        cmd : str
            Device command without its write termination.

        Returns
        -------
        response : str
            The unparsed PyVISA response, with read termination removed.
        """
        if self._instr is None:
            raise RuntimeError(_NOT_CONNECTED)
        return self._instr.query(cmd)

    def _read_bytes(self, count: int) -> bytes:
        """Read bytes over the active connection.

        Parameters
        ----------
        count : int
            Number of bytes to read.

        Returns
        -------
        data : bytes
            The bytes read from the instrument.
        """
        if self._instr is None:
            raise RuntimeError(_NOT_CONNECTED)
        return self._instr.read_bytes(count)

    @contextmanager
    def _extended_timeout(self, minimum_ms: float) -> Iterator[None]:
        """Temporarily extend the VISA timeout for an operation.

        Preserve a longer or infinite caller timeout. Restore the previous
        timeout on exit; if restoration fails during another exception, log
        the restoration failure and preserve the original exception.

        Parameters
        ----------
        minimum_ms : float
            Finite, nonnegative minimum timeout in ms.

        Yields
        ------
        context : None
            Control to the operation using the temporary timeout.
        """
        instr = self._instr
        if instr is None:
            raise RuntimeError(_NOT_CONNECTED)
        minimum_ms = _to_finite_float(minimum_ms)
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
        """Query the first response value without its leading space or unit.

        Parameters
        ----------
        cmd : str
            Device command without its write termination.

        Returns
        -------
        value : str
            The first response value as text; numeric conversion is left to
            the caller.
        """
        return self._query(cmd)[1:].split(" ")[0]

    def _query_manual(self, cmd: str) -> str:
        """Read a command response until the complete device terminator.

        Read one byte at a time so partial termination sequences inside
        information responses do not end the read.

        Parameters
        ----------
        cmd : str
            Device command without its write termination.

        Returns
        -------
        response : str
            ASCII response text without the terminator or outer whitespace.
            Internal line breaks and units are preserved.
        """
        resp = b""
        self._write(cmd)
        terminator = READ_TERMINATION.encode(ENCODING)
        while not resp.endswith(terminator):
            resp += self._read_bytes(1)

        return resp.decode(ENCODING).removesuffix(READ_TERMINATION).strip()

    @property
    def scan_speed(self) -> float:
        """Get the grating scan speed.

        Returns
        -------
        scan_speed : float
            Scan speed in nm/min.
        """
        return float(self._query_value("?NM/MIN"))

    @scan_speed.setter
    def scan_speed(self, speed: Number) -> None:
        """Set the grating scan speed.

        Parameters
        ----------
        speed : float or str
            Finite scan speed in nm/min. The driver formats this to one
            decimal place; the rounded value must be positive. This is a
            driver convention, not a verified device resolution.
        """
        speed = round(_to_finite_float(speed), 1)
        if speed <= 0:
            raise ValueError("Scan speed must be positive after rounding to one decimal place")
        self._query(f"{speed:.1f} NM/MIN")

    def scan_to_wavelength(self, wavelength: Number) -> None:
        """Scan the grating to a target wavelength.

        Estimate duration from the current wavelength and finite, positive
        scan speed. Temporarily extend the timeout using that duration plus
        `scan_timeout_buffer_ms`, then restore the previous timeout.

        Parameters
        ----------
        wavelength : float or str
            Finite target wavelength in nm, rounded to one decimal place.
        """
        wavelength = round(_to_finite_float(wavelength), 1)
        if self._instr is None:
            raise RuntimeError(_NOT_CONNECTED)
        buffer_ms = _to_finite_float(self.scan_timeout_buffer_ms)
        if buffer_ms < 0:
            raise ValueError("Scan timeout buffer must be nonnegative")
        # calculate scan time in ms
        current_wavelength = self.wavelength
        speed = _to_finite_float(self.scan_speed)
        if speed <= 0:
            raise ValueError("Reported scan speed must be positive")
        scan_time = abs(wavelength - current_wavelength) * 60000 / speed

        with self._extended_timeout(scan_time + buffer_ms):
            self._query(f"{wavelength:.1f} NM")

    @property
    def wavelength(self) -> float:
        """Get the current wavelength.

        Returns
        -------
        wavelength : float
            Wavelength in nm.
        """
        return float(self._query_value("?NM"))

    @wavelength.setter
    def wavelength(self, wavelength: Number) -> None:
        """Position the grating at a wavelength.

        Parameters
        ----------
        wavelength : float or str
            Finite target wavelength in nm, rounded to one decimal place.
        """
        self._query(f"{_to_finite_float(wavelength):.1f} GOTO")

    @property
    def grating(self) -> int:
        """Get the selected grating number.

        Returns
        -------
        grating : int
            Grating number on the active turret.
        """
        return int(self._query_value("?GRATING"))

    @grating.setter
    def grating(self, grating: Integer) -> None:
        """Select a grating on the active turret.

        Temporarily extend the timeout using `grating_timeout_ms`.

        Parameters
        ----------
        grating : int or str
            Grating number, converted to an integer.
        """
        command = f"{int(grating)} GRATING"
        with self._extended_timeout(self.grating_timeout_ms):
            self._query(command)

    @property
    def turret(self) -> int:
        """Get the selected turret number.

        Returns
        -------
        turret : int
            Turret number.
        """
        return int(self._query_value("?TURRET"))

    @turret.setter
    def turret(self, turret: Integer) -> None:
        """Select the turret parameters.

        Parameters
        ----------
        turret : int or str
            Turret number, converted to an integer.
        """
        self._query(f"{int(turret)} TURRET")

    @property
    def grating_info(self) -> str:
        """Get the grating information.

        Returns
        -------
        grating_info : str
            Text describing groove spacing and blaze wavelength for each
            grating. Internal line breaks are preserved.
        """
        return self._query_manual("?GRATINGS")

    @property
    def turret_info(self) -> str:
        """Get the turret information.

        Returns
        -------
        turret_info : str
            Text describing grating groove spacing for each turret.
            Internal line breaks are preserved.
        """
        return self._query_manual("?TURRETS")

    @property
    def filter(self) -> int:
        """Get the filter wheel position.

        Returns
        -------
        filter_pos : int
            Filter position number.
        """
        return int(self._query_value("?FILTER"))

    @filter.setter
    def filter(self, filter_pos: Integer) -> None:
        """Select a filter wheel position.

        Temporarily extend the timeout using `filter_timeout_ms`.

        Parameters
        ----------
        filter_pos : int or str
            Filter position number, converted to an integer.
        """
        command = f"{int(filter_pos)} FILTER"
        with self._extended_timeout(self.filter_timeout_ms):
            self._query(command)

    def home_filter(self) -> None:
        """Home the filter wheel to its first position.

        Temporarily extend the timeout using `filter_home_timeout_ms`.
        """
        with self._extended_timeout(self.filter_home_timeout_ms):
            self._query("FHOME")
