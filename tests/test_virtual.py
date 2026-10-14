"""Simulator state and lifecycle needed by simulated experiments."""

import pytest
from unittest.mock import patch
from virtual_sp2150 import sp2150


def test_initial_state(virtual_device):
    assert virtual_device.scan_speed == 1000.0
    assert virtual_device.wavelength == 0.0
    assert virtual_device.grating == 1
    assert virtual_device.turret == 1
    assert virtual_device.filter == 1


def test_instances_are_independent(virtual_device):
    with sp2150() as other:
        other.connect('virtual')
        virtual_device.wavelength = 532
        virtual_device.filter = 3
        assert other.wavelength == 0.0
        assert other.filter == 1


def test_reconnect_preserves_instrument_state(virtual_device):
    virtual_device.wavelength = 532
    virtual_device.grating = 2
    virtual_device.disconnect()
    virtual_device.connect('virtual')
    assert virtual_device.wavelength == 532.0
    assert virtual_device.grating == 2


def test_context_manager_disconnects_on_exception(virtual_device):
    with pytest.raises(ValueError, match='experiment failed'):
        with virtual_device as entered:
            assert entered is virtual_device
            raise ValueError('experiment failed')
    with pytest.raises(RuntimeError):
        _ = virtual_device.wavelength


def test_one_decimal_precision_matches_driver_commands(virtual_device):
    virtual_device.wavelength = '532.26'
    virtual_device.scan_speed = '123.46'
    assert virtual_device.wavelength == 532.3
    assert virtual_device.scan_speed == 123.5
    virtual_device.scan_to_wavelength('533.26')
    assert virtual_device.wavelength == 533.3


@pytest.mark.parametrize('name', ('wavelength', 'scan_speed', 'grating', 'turret', 'filter'))
def test_invalid_numeric_values_preserve_previous_state(virtual_device, name):
    original = getattr(virtual_device, name)
    with pytest.raises(ValueError):
        setattr(virtual_device, name, 'not-a-number')
    assert getattr(virtual_device, name) == original


def test_simulated_experiment_never_constructs_a_resource_manager():
    with patch('pyvisa.ResourceManager') as manager:
        with sp2150() as device:
            device.connect('ASRL2::INSTR', timeout=30000)
            device.grating = 2
            device.filter = 3
            readings = []
            for wavelength in (500, 501, 502):
                device.scan_to_wavelength(wavelength)
                readings.append(device.wavelength)
        assert readings == [500.0, 501.0, 502.0]
        manager.assert_not_called()
