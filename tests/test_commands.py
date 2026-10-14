"""Check exact wire commands independently of the shared behavioral contract."""

import pytest


@pytest.mark.parametrize(
    'name,command',
    list(
        {
            'scan_speed': '?NM/MIN',
            'wavelength': '?NM',
            'grating': '?GRATING',
            'turret': '?TURRET',
            'filter': '?FILTER'
        }.items(
        )
    )
)
def test_property_getter_commands(connected_driver, resource, name, command):
    getattr(connected_driver, name)
    assert resource.commands.pop() == command


@pytest.mark.parametrize(
    'name,value,command',
    (
        (
            'scan_speed',
            '123.46',
            '123.5 NM/MIN'
        ),
        (
            'wavelength',
            '532.26',
            '532.3 GOTO'
        ),
        (
            'grating',
            '2',
            '2 GRATING'
        ),
        (
            'turret',
            '1',
            '1 TURRET'
        ),
        (
            'filter',
            '3',
            '3 FILTER'
        )
    )
)
def test_property_setter_commands(connected_driver, resource, name, value, command):
    setattr(connected_driver, name, value)
    assert resource.commands.pop() == command


def test_scan_command_and_readback(connected_driver, resource):
    connected_driver.scan_to_wavelength('532.26')
    assert resource.commands == ['?NM', '?NM/MIN', '532.3 NM']
    assert connected_driver.wavelength == 532.3


def test_home_command(connected_driver, resource):
    connected_driver.home_filter()
    assert resource.commands == ['FHOME']


def test_query_preserves_response_while_property_parses_value(connected_driver):
    assert connected_driver._query('?NM/MIN') == ' 1000.0 nm/min'
    assert connected_driver.scan_speed == 1000.0


@pytest.mark.parametrize(
    'method,argument',
    (
        (
            '_write',
            '?TURRETS'
        ),
        (
            '_query',
            'FHOME'
        ),
        (
            '_read_bytes',
            1
        )
    )
)
def test_disconnected_communication_does_not_reach_resource(
    connected_driver,
    resource,
    method,
    argument
):
    connected_driver.disconnect()
    with pytest.raises(RuntimeError, match='not connected'):
        getattr(connected_driver, method)(argument)
    assert resource.commands == []
    assert resource._pending == b''


@pytest.mark.parametrize(
    'name,command',
    (
        (
            'grating_info',
            '?GRATINGS'
        ),
        (
            'turret_info',
            '?TURRETS'
        )
    )
)
def test_information_commands_preserve_internal_newlines_and_trailing_letters(
    connected_driver,
    resource,
    name,
    command
):
    assert getattr(connected_driver, name) == getattr(resource, name)
    assert resource.commands.pop() == command
    assert resource._pending == b''


def test_incomplete_information_response_propagates_timeout(connected_driver, resource):
    original_write = resource.write

    def incomplete_write(command):
        original_write(command)
        resource._pending = b' partial response\r\n'
    resource.write = incomplete_write
    with pytest.raises(TimeoutError):
        _ = connected_driver.turret_info
