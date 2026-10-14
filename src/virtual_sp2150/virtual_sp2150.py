"""In-memory simulation of an Acton SP-2150 monochromator."""

from __future__ import annotations

from types import TracebackType
from typing import Any

import pyvisa
from sp2150.sp2150 import (
    Integer, Number, _NOT_CONNECTED, _discard_fixed_options, _finite_number,
)


class sp2150:
    """Simulate an Acton SP-2150 monochromator and FA-2448 filter wheel.

    Connect before using instrument commands. Operations update memory
    immediately. Timeout attributes are accepted for API compatibility
    and do not affect simulation timing.

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
        """Create a disconnected simulator with default instrument state."""
        self.grating_timeout_ms: float = 30000.0
        self.filter_timeout_ms: float = 10000.0
        self.filter_home_timeout_ms: float = 20000.0
        self.scan_timeout_buffer_ms: float = 5000.0
        self._scan_speed = 1000.0
        self._wavelength = 0.0
        self._grating = 1
        self._turret = 1
        self._grating_info = "dummy info"
        self._turret_info = "dummy info"
        self._filter = 1

        self._instr: None = None
        self._connected = False

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

        Parameters
        ----------
        exc_type : type or None
            Exception type from the context body, or None on normal exit.
        exc_value : BaseException or None
            Exception from the context body, or None on normal exit.
        traceback : types.TracebackType or None
            Traceback from the context body, or None on normal exit.
        """
        self.disconnect()

    def connect(
        self,
        resource_name: str,
        *,
        resource_manager: pyvisa.ResourceManager | None = None,
        **resource_kwargs: Any,
    ) -> None:
        """Connect the simulated instrument without contacting hardware.

        Disconnect before reconnecting. Instrument state persists across
        disconnection and reconnection.

        Parameters
        ----------
        resource_name : str
            Resource name accepted for compatibility with the hardware driver.
            The simulator does not interpret it.
        resource_manager : pyvisa.ResourceManager or None, optional
            Accepted for API compatibility; never used or closed.
        **resource_kwargs
            Accepted without opening a VISA backend. Fixed device settings
            and resource class overrides warn and are ignored, as in the
            driver. Other options are ignored without backend validation.
        """
        if self._connected:
            raise RuntimeError("Already connected; disconnect before reconnecting")
        _discard_fixed_options(resource_kwargs)
        self._connected = True

    def disconnect(self) -> None:
        """Disconnect the simulated instrument; repeated calls are harmless.

        Instrument state is preserved for the next connection.
        """
        self._connected = False

    def _check_connection(self) -> None:
        """Check that the simulated instrument is connected."""
        if not self._connected:
            raise RuntimeError(_NOT_CONNECTED)

    @property
    def scan_speed(self) -> float:
        """Get the grating scan speed.

        Returns
        -------
        scan_speed : float
            Scan speed in nm/min.
        """
        self._check_connection()
        return self._scan_speed

    @scan_speed.setter
    def scan_speed(self, speed: Number) -> None:
        """Set the grating scan speed.

        Parameters
        ----------
        speed : float or str
            Finite scan speed in nm/min. Rounded to one decimal place;
            the rounded value must be positive.
        """
        self._check_connection()
        speed = round(_finite_number(speed, "Scan speed"), 1)
        if speed <= 0:
            raise ValueError("Scan speed must be positive at the device's one-decimal precision")
        self._scan_speed = speed

    def scan_to_wavelength(self, wavelength: Number) -> None:
        """Simulate a scan to a target wavelength.

        Update the wavelength immediately without simulating movement time.

        Parameters
        ----------
        wavelength : float or str
            Finite target wavelength in nm, rounded to one decimal place.
        """
        self.wavelength = wavelength

    @property
    def wavelength(self) -> float:
        """Get the current wavelength.

        Returns
        -------
        wavelength : float
            Wavelength in nm.
        """
        self._check_connection()
        return self._wavelength

    @wavelength.setter
    def wavelength(self, wavelength: Number) -> None:
        """Position the grating at a wavelength.

        Parameters
        ----------
        wavelength : float or str
            Finite target wavelength in nm, rounded to one decimal place.
        """
        self._check_connection()
        self._wavelength = float(f"{_finite_number(wavelength, 'Wavelength'):.1f}")

    @property
    def grating(self) -> int:
        """Get the selected grating number.

        Returns
        -------
        grating : int
            Grating number on the active turret.
        """
        self._check_connection()
        return self._grating

    @grating.setter
    def grating(self, grating: Integer) -> None:
        """Select a grating on the active turret.

        Parameters
        ----------
        grating : int or str
            Grating number, converted to an integer.
        """
        self._check_connection()
        self._grating = int(grating)

    @property
    def turret(self) -> int:
        """Get the selected turret number.

        Returns
        -------
        turret : int
            Turret number.
        """
        self._check_connection()
        return self._turret

    @turret.setter
    def turret(self, turret: Integer) -> None:
        """Select the turret parameters.

        Parameters
        ----------
        turret : int or str
            Turret number, converted to an integer.
        """
        self._check_connection()
        self._turret = int(turret)

    @property
    def grating_info(self) -> str:
        """Get simulated grating information.

        Returns
        -------
        grating_info : str
            Placeholder grating information text.
        """
        self._check_connection()
        return self._grating_info

    @property
    def turret_info(self) -> str:
        """Get simulated turret information.

        Returns
        -------
        turret_info : str
            Placeholder turret information text.
        """
        self._check_connection()
        return self._turret_info

    @property
    def filter(self) -> int:
        """Get the filter wheel position.

        Returns
        -------
        filter_pos : int
            Filter position number.
        """
        self._check_connection()
        return self._filter

    @filter.setter
    def filter(self, filter_pos: Integer) -> None:
        """Select a filter wheel position.

        Parameters
        ----------
        filter_pos : int or str
            Filter position number, converted to an integer.
        """
        self._check_connection()
        self._filter = int(filter_pos)

    def home_filter(self) -> None:
        """Home the filter wheel to its first position."""
        self._check_connection()
        self._filter = 1
