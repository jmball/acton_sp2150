"""Reject invalid numeric commands before changing instrument state."""

import pytest


@pytest.mark.parametrize("value", [0, -1, -0.01, 0.01, 0.049, "0", "0.01", "bad",
                                  float("nan"), float("inf"), float("-inf"), "nan", "inf"])
def test_invalid_scan_speed_preserves_state_and_sends_no_command(instrument, resource, value):
    original = instrument.scan_speed
    previous_commands = resource.commands.copy()
    with pytest.raises(ValueError):
        instrument.scan_speed = value
    assert resource.commands == previous_commands
    assert instrument.scan_speed == original


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf"), "nan", "inf", "-inf", "bad"])
@pytest.mark.parametrize("operation", ["goto", "scan"])
def test_nonfinite_wavelengths_and_scan_targets_send_no_commands(instrument, resource, value, operation):
    original = instrument.wavelength
    previous_commands = resource.commands.copy()
    with pytest.raises(ValueError):
        if operation == "goto":
            instrument.wavelength = value
        else:
            instrument.scan_to_wavelength(value)
    assert resource.commands == previous_commands
    assert instrument.wavelength == original


def test_valid_values_retain_device_precision(instrument):
    for value, expected in (("0.06", 0.1), (123.46, 123.5)):
        instrument.scan_speed = value
        assert instrument.scan_speed == expected
    instrument.wavelength = "532.26"
    assert instrument.wavelength == 532.3
    instrument.scan_to_wavelength("0")
    assert instrument.wavelength == 0.0


@pytest.mark.parametrize("speed", [0, -1, float("nan"), float("inf"), float("-inf")])
def test_invalid_reported_scan_speed_stops_before_scan_or_timeout_change(connected_driver, resource, speed):
    resource.scan_speed = speed
    resource.commands.clear()
    old_timeout = resource.timeout
    with pytest.raises(ValueError, match="Reported scan speed"):
        connected_driver.scan_to_wavelength(500)
    assert resource.commands == ["?NM", "?NM/MIN"]
    assert resource.timeout == old_timeout
    assert resource.wavelength == 0.0
