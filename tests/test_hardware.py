"""Explicitly enabled real hardware commands and parametrised homing timings."""

import pytest

from tests.contract import (
    test_scan_speed, test_direct_wavelength, test_scanned_wavelength, test_grating,
    test_turret, test_filter, test_home_filter, test_grating_information,
    test_turret_information,
)
from tests.hardware import measure_homing

pytestmark = pytest.mark.hardware


@pytest.fixture
def instrument(hardware_device):
    return hardware_device


@pytest.fixture
def targets(hardware_options):
    return hardware_options


def test_home_filter_timing(hardware_device, hardware_options, home_start_position,
                            home_repeat, pytestconfig, record_property):
    measurement = measure_homing(hardware_device, home_start_position, home_repeat, pytestconfig)
    record_property("homing_start_position", home_start_position)
    record_property("homing_repeat", home_repeat)
    record_property("homing_elapsed_ms", measurement.elapsed_ms)
    record_property("homing_allowance_ms", measurement.allowance_ms)
    assert hardware_device.filter == hardware_options.home_filter_position
    assert measurement.elapsed_ms <= measurement.allowance_ms, "Homing exceeded its timeout allowance"
