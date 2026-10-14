"""Check operation-specific timeouts while commands execute and after failures."""

import pytest
import math
from unittest.mock import patch
from pyvisa import constants
from virtual_sp2150 import sp2150 as virtual_sp2150


@pytest.mark.parametrize(
    'name,value',
    (
        (
            'grating_timeout_ms',
            30000
        ),
        (
            'filter_timeout_ms',
            10000
        ),
        (
            'filter_home_timeout_ms',
            20000
        ),
        (
            'scan_timeout_buffer_ms',
            5000
        )
    )
)
def test_defaults_match_simulator_and_instances_are_independent(connected_driver, name, value):
    simulated = virtual_sp2150()
    assert getattr(connected_driver, name) == value
    assert getattr(simulated, name) == value
    setattr(connected_driver, name, value + 1)
    assert getattr(simulated, name) == value


def test_fixed_operations_extend_and_restore_timeout(connected_driver, observed, resource):
    connected_driver.grating = 2
    connected_driver.filter = 3
    connected_driver.home_filter()
    assert observed == [('2 GRATING', 30000), ('3 FILTER', 10000), ('FHOME', 20000)]
    assert resource.timeout == 1000


def test_custom_operation_allowances_are_used(connected_driver, observed, resource):
    connected_driver.grating_timeout_ms = 41000
    connected_driver.filter_timeout_ms = 12000
    connected_driver.filter_home_timeout_ms = 25000
    connected_driver.grating = 2
    connected_driver.filter = 3
    connected_driver.home_filter()
    assert observed == [('2 GRATING', 41000), ('3 FILTER', 12000), ('FHOME', 25000)]
    assert resource.timeout == 1000


def test_fixed_operations_restore_timeout_after_command_failure(connected_driver, resource):
    for command, operation in (
        (
            '2 GRATING',
            lambda: setattr(
                connected_driver,
                'grating',
                2
            )
        ),
        (
            '3 FILTER',
            lambda: setattr(
                connected_driver,
                'filter',
                3
            )
        ),
        (
            'FHOME',
            connected_driver.home_filter
        )
    ):
        resource.fail_command = command
        with pytest.raises(TimeoutError):
            operation()
        assert resource.timeout == 1000


@pytest.mark.parametrize('timeout', (60000, None))
def test_longer_and_infinite_caller_timeouts_are_preserved(
    connected_driver,
    observed,
    resource,
    timeout
):
    resource.timeout = timeout
    old_timeout = resource.timeout
    with patch.object(resource, 'set_visa_attribute', wraps=resource.set_visa_attribute) as setter:
        connected_driver.grating = 2
        connected_driver.filter = 3
        connected_driver.home_filter()
        connected_driver.scan_to_wavelength(1)
        setter.assert_not_called()
    assert resource.timeout == old_timeout
    assert all((value == old_timeout for _, value in observed))
    observed.clear()


def test_scan_uses_duration_plus_custom_buffer_even_when_duration_is_short(
    connected_driver,
    observed,
    resource
):
    resource.scan_speed = 600
    connected_driver.scan_timeout_buffer_ms = 1500
    connected_driver.scan_to_wavelength(1)
    assert observed == [('?NM', 1000), ('?NM/MIN', 1000), ('1.0 NM', 1600)]
    assert resource.timeout == 1000


def test_scan_buffer_can_be_zero(connected_driver, observed, resource):
    connected_driver.scan_timeout_buffer_ms = 0
    connected_driver.scan_to_wavelength(100)
    assert observed[-1] == ('100.0 NM', 6000)
    assert resource.timeout == 1000


def test_scan_duration_uses_the_wavelength_sent_to_hardware(connected_driver, observed, resource):
    resource.scan_speed = 600
    connected_driver.scan_timeout_buffer_ms = 0
    resource.timeout = 1
    connected_driver.scan_to_wavelength(0.06)
    assert observed[-1] == ('0.1 NM', 10)
    assert resource.timeout == 1


@pytest.mark.parametrize('buffer', (-1, math.inf, math.nan))
def test_invalid_buffer_is_rejected_before_io(connected_driver, observed, resource, buffer):
    connected_driver.scan_timeout_buffer_ms = buffer
    with pytest.raises(ValueError):
        connected_driver.scan_to_wavelength(100)
    assert observed == []
    assert resource.timeout == 1000


def test_initial_timeout_assignment_failure_sends_no_command(connected_driver, observed, resource):
    resource.fail_attribute = constants.ResourceAttribute.timeout_value
    with pytest.raises(ValueError, match='attribute rejected'):
        connected_driver.grating = 2
    assert observed == []
    assert resource.timeout == 1000


def test_restoration_failure_preserves_active_command_error(caplog, connected_driver, resource):
    original_query = resource.query

    def query(command):
        if command == '2 GRATING':
            resource.fail_attribute = constants.ResourceAttribute.timeout_value
            raise TimeoutError('original command error')
        return original_query(command)
    resource.query = query
    with caplog.at_level(
        'WARNING',
        logger='sp2150.sp2150'
    ), pytest.raises(
        TimeoutError,
        match='original command error'
    ):
        connected_driver.grating = 2
    assert 'Failed to restore the instrument timeout after an error' in caplog.text
    assert caplog.records[-1].exc_info is not None


def test_restoration_failure_is_raised_when_command_succeeds(connected_driver, resource):
    original_query = resource.query

    def query(command):
        result = original_query(command)
        resource.fail_attribute = constants.ResourceAttribute.timeout_value
        return result
    resource.query = query
    with pytest.raises(ValueError, match='attribute rejected'):
        connected_driver.grating = 2
    assert resource.grating == 2
