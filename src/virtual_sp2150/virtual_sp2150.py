"""Acton SP2150 monochromator control library."""

from __future__ import annotations

from types import TracebackType
from typing import Any

import pyvisa
from sp2150.sp2150 import (
    Integer, Number, _NOT_CONNECTED, _OperationTimeouts, _discard_fixed_options, _finite_number,
    _scan_speed_value,
)


class sp2150(_OperationTimeouts):
    """Monochromator instrument object."""

    def __init__(self) -> None:
        """Initialise with dummy parameters."""
        super().__init__()
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
            settings and resource class overrides warn like the driver;
            other options are not validated by the simulator.
        """
        if self._connected:
            raise RuntimeError("Already connected; disconnect before reconnecting")
        _discard_fixed_options(resource_kwargs)
        self._connected = True

    def disconnect(self) -> None:
        """Disconnect instrument."""
        self._connected = False

    def _check_connection(self) -> None:
        """Require the same connection state as the hardware driver."""
        if not self._connected:
            raise RuntimeError(_NOT_CONNECTED)

    @property
    def scan_speed(self) -> float:
        """Get grating scan speed in nm/min."""
        self._check_connection()
        return self._scan_speed

    @scan_speed.setter
    def scan_speed(self, speed: Number) -> None:
        """Set finite scan speed in nm/min, positive after one-decimal rounding."""
        self._check_connection()
        self._scan_speed = _scan_speed_value(speed)

    def scan_to_wavelength(self, wavelength: Number) -> None:
        """Scan grating to a finite wavelength in nm."""
        self.wavelength = wavelength

    @property
    def wavelength(self) -> float:
        """Get current grating wavelength position in nm."""
        self._check_connection()
        return self._wavelength

    @wavelength.setter
    def wavelength(self, wavelength: Number) -> None:
        """Set grating position to a finite wavelength in nm."""
        self._check_connection()
        self._wavelength = float(f"{_finite_number(wavelength, 'Wavelength'):.1f}")

    @property
    def grating(self) -> int:
        """Get grating number."""
        self._check_connection()
        return self._grating

    @grating.setter
    def grating(self, grating: Integer) -> None:
        """Set grating number."""
        self._check_connection()
        self._grating = int(grating)

    @property
    def turret(self) -> int:
        """Get turret number."""
        self._check_connection()
        return self._turret

    @turret.setter
    def turret(self, turret: Integer) -> None:
        """Set turrent number."""
        self._check_connection()
        self._turret = int(turret)

    @property
    def grating_info(self) -> str:
        """Get groove spacing and blaze wavelength of each grating."""
        self._check_connection()
        return self._grating_info

    @property
    def turret_info(self) -> str:
        """Get groove spacing of each grating on each turret."""
        self._check_connection()
        return self._turret_info

    @property
    def filter(self) -> int:
        """Get filter wheel position number."""
        self._check_connection()
        return self._filter

    @filter.setter
    def filter(self, filter_pos: Integer) -> None:
        """Set filter wheel position number."""
        self._check_connection()
        self._filter = int(filter_pos)

    def home_filter(self) -> None:
        """Set filter wheel to home position."""
        self._check_connection()
        self._filter = 1
