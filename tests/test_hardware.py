"""Hardware command tests and filter-homing timings.

Supplying --resource-name enables hardware tests. Without it these tests
skip, while the normal suite exercises the simulator and fake driver.
Collection alone never connects. Before the first hardware session, inspect
and save the raw ?GRATINGS and ?TURRETS replies to establish their layout
and a defensible response-size bound. Keep per-character read timeouts.
Tests move the instrument and attempt to
restore its original state after each case.

The default configuration selects grating 1 on turret 1. The grating and
turret overrides select positions/parameter sets, not counts; they do not
infer which interchangeable turrets are physically installed.

Parameters
----------
--resource-name : str
    VISA resource name or alias. Required to enable hardware access.
--visa-backend : str, optional
    Backend such as @py. Omit to use the system-selected backend. Pass
    --visa-backend=@py with an equals sign for pytest.
--wavelength : float, optional
    Direct-positioning target in nm. Default is 500.
--scan-wavelength : float, optional
    Scan target in nm, distinct at 0.1 nm precision. Default is 501.
--scan-speed : float, optional
    Scan speed in nm/min, positive after rounding. Default is 600.
--grating : int, optional
    Installed grating number to select and test. Default is 1.
--turret : int, optional
    Turret parameter set matching the installed turret. Default is 1.
--filter-position : int, optional
    Filter position used by selection tests. Default is 3. The homing
    timing test independently covers all six starting positions.
--home-filter-position : int, optional
    Expected position after homing. Default is 1.
--timeout : int, optional
    General I/O timeout in ms. Default is 30000.
--home-repetitions : int, optional
    Number of timing sweeps through all six positions. Default is 1.
--filter-home-timeout-ms : int, optional
    Override the driver's homing allowance in ms. The timing test applies
    this allowance exactly, even when the general timeout is longer.
--resource-option : str, optional
    Additional VISA option as KEY=JSON; repeat for multiple options.
    Fixed device settings warn and are ignored.
"""

import pytest

from tests.contract import (
    test_scan_speed,
    test_direct_wavelength,
    test_scanned_wavelength,
    test_grating,
    test_turret,
    test_filter,
    test_home_filter,
    test_grating_information,
    test_turret_information,
)
from tests.hardware_plugin import measure_homing

pytestmark = pytest.mark.hardware


@pytest.fixture
def instrument(hardware_device):
    return hardware_device


@pytest.fixture
def targets(hardware_options):
    return hardware_options


def test_home_filter_timing(
    hardware_device,
    hardware_options,
    home_start_position,
    home_repeat,
    pytestconfig,
    record_property,
):
    measurement = measure_homing(
        hardware_device, home_start_position, home_repeat, pytestconfig
    )
    record_property("homing_start_position", home_start_position)
    record_property("homing_repeat", home_repeat)
    record_property("homing_elapsed_ms", measurement.elapsed_ms)
    record_property("homing_allowance_ms", measurement.allowance_ms)
    assert hardware_device.filter == hardware_options.home_filter_position
    assert measurement.elapsed_ms <= measurement.allowance_ms, (
        "Homing exceeded its timeout allowance"
    )
