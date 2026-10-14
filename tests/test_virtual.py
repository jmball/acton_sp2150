"""Simulator state, lifecycle, and simulated experiments without VISA I/O."""

from unittest.mock import patch

import pytest

from virtual_sp2150 import sp2150


def test_initial_state(virtual_device):
    assert virtual_device.scan_speed == 1000.0
    assert virtual_device.wavelength == 0.0
    assert virtual_device.grating == 1
    assert virtual_device.turret == 1
    assert virtual_device.filter == 1


def test_instances_are_independent(virtual_device):
    with sp2150() as other:
        other.connect("virtual")
        virtual_device.wavelength = 532
        virtual_device.filter = 3
        assert other.wavelength == 0.0
        assert other.filter == 1


def test_reconnect_preserves_instrument_state(virtual_device):
    virtual_device.wavelength = 532
    virtual_device.grating = 2
    virtual_device.disconnect()
    virtual_device.connect("virtual")
    assert virtual_device.wavelength == 532.0
    assert virtual_device.grating == 2


def test_context_manager_disconnects_on_exception(virtual_device):
    with pytest.raises(ValueError, match="experiment failed"):
        with virtual_device as entered:
            assert entered is virtual_device
            raise ValueError("experiment failed")
    with pytest.raises(RuntimeError):
        _ = virtual_device.wavelength


def test_simulated_experiment_never_constructs_a_resource_manager():
    with patch("pyvisa.ResourceManager") as manager:
        with sp2150() as device:
            device.connect("ASRL2::INSTR", timeout=30000)
            device.grating = 2
            device.filter = 3
            readings = []
            for wavelength in (500, 501, 502):
                device.scan_to_wavelength(wavelength)
                readings.append(device.wavelength)
        assert readings == [500.0, 501.0, 502.0]
        manager.assert_not_called()


def test_simulator_validates_options_and_reconnection_without_hardware():
    device = sp2150()
    with patch("pyvisa.ResourceManager") as factory:
        with pytest.warns(UserWarning, match="baud_rate"):
            device.connect("ASRL2::INSTR", baud_rate=9600)
        device.disconnect()
        device.connect("ASRL2::INSTR", timeout=2000)
        with pytest.raises(RuntimeError):
            device.connect("ASRL2::INSTR")
        device.disconnect()
        device.disconnect()
        device.connect("dummy")
        factory.assert_not_called()
    device.scan_to_wavelength("532")
    device.grating = "2"
    assert device.wavelength == 532.0
    assert device.grating == 2


def test_simulator_ignores_backend_options_without_generic_validation():
    device = sp2150()
    device.connect("GPIB0::14::INSTR", enable_repeat_addressing=True)
    device.disconnect()
    device.connect(
        "ASRL2::INSTR", enable_repeat_addressing=True, future_backend_option=1
    )
