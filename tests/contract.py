"""Pytest commands shared by simulator, fake-backed driver, and real hardware."""

from dataclasses import dataclass

import pytest


@dataclass
class ContractTargets:
    wavelength: float = 500.0
    scan_wavelength: float = 501.0
    scan_speed: float = 600.0
    grating: int = 2
    turret: int = 1
    filter_position: int = 3
    home_filter_position: int = 1


def test_scan_speed(instrument, targets):
    instrument.scan_speed = str(targets.scan_speed)
    assert isinstance(instrument.scan_speed, float)
    assert instrument.scan_speed == pytest.approx(targets.scan_speed, abs=0.11, rel=0)


def test_direct_wavelength(instrument, targets):
    instrument.wavelength = str(targets.wavelength)
    assert isinstance(instrument.wavelength, float)
    assert instrument.wavelength == pytest.approx(targets.wavelength, abs=0.11, rel=0)


def test_scanned_wavelength(instrument, targets):
    instrument.wavelength = targets.wavelength
    instrument.scan_speed = targets.scan_speed
    instrument.scan_to_wavelength(str(targets.scan_wavelength))
    assert instrument.wavelength == pytest.approx(
        targets.scan_wavelength, abs=0.11, rel=0
    )


def test_grating(instrument, targets):
    instrument.turret = targets.turret
    instrument.grating = str(targets.grating)
    assert isinstance(instrument.grating, int)
    assert instrument.grating == targets.grating


def test_turret(instrument, targets):
    instrument.turret = str(targets.turret)
    assert isinstance(instrument.turret, int)
    assert instrument.turret == targets.turret


def test_filter(instrument, targets):
    instrument.filter = str(targets.filter_position)
    assert isinstance(instrument.filter, int)
    assert instrument.filter == targets.filter_position


def test_home_filter(instrument, targets):
    instrument.filter = targets.filter_position
    instrument.home_filter()
    assert instrument.filter == targets.home_filter_position


def test_grating_information(instrument):
    assert isinstance(instrument.grating_info, str)
    assert instrument.grating_info.strip()


def test_turret_information(instrument):
    assert isinstance(instrument.turret_info, str)
    assert instrument.turret_info.strip()
