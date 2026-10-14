"""Connection and protocol regressions using VISA classes without a backend."""

import pytest
from unittest.mock import Mock, patch
from pyvisa import constants
from pyvisa.resources import Resource
from sp2150 import sp2150
from virtual_sp2150 import sp2150 as virtual_sp2150
from tests.fakes import FakeMessage, make_manager


@pytest.mark.parametrize('driver', (sp2150, virtual_sp2150))
def test_manager_is_keyword_only_in_both_drivers(manager, driver):
    with pytest.raises(TypeError):
        driver().connect('ASRL2::INSTR', manager)


def test_serial_settings_and_protocol_are_applied_before_first_query(connect, resource):
    original_query = resource.query

    def query(command):
        assert resource.baud_rate == 9600
        assert resource.data_bits == 8
        assert resource.parity == constants.Parity.none
        assert resource.stop_bits == constants.StopBits.one
        assert resource.flow_control == constants.ControlFlow.none
        assert resource.end_input == constants.SerialTermination.termination_char
        assert resource.end_output == constants.SerialTermination.none
        assert resource.write_termination == '\r'
        assert resource.read_termination == ' ok\r\n'
        assert resource.encoding == 'ASCII'
        return original_query(command)
    resource.query = query
    connect(timeout=5000, query_delay=0.1, chunk_size=512)
    assert resource.commands == ['NO-ECHO']
    assert resource.timeout == 5000
    assert resource.query_delay == 0.1
    assert resource.chunk_size == 512


@pytest.mark.parametrize(
    'name,value',
    list(
        {
            'read_termination': ' ok\r\n',
            'write_termination': '\r',
            'encoding': 'ASCII',
            'baud_rate': 9600,
            'data_bits': 8,
            'parity': constants.Parity.none,
            'stop_bits': constants.StopBits.one,
            'flow_control': constants.ControlFlow.none,
            'end_input': constants.SerialTermination.termination_char,
            'end_output': constants.SerialTermination.none
        }.items(
        )
    )
)
def test_fixed_options_warn_and_are_ignored_even_when_matching_defaults(
    connect,
    manager,
    resource,
    unconnected_driver,
    name,
    value
):
    with pytest.warns(UserWarning, match=name):
        connect(**{name: value})
    manager.open_resource.assert_called_with('serial-alias')
    assert unconnected_driver._instr is resource
    unconnected_driver.disconnect()
    simulator = virtual_sp2150()
    with pytest.warns(UserWarning, match=name):
        simulator.connect('dummy', **{name: value})
    assert simulator.wavelength == 0.0
    simulator.disconnect()


def test_conflicting_fixed_options_are_removed_before_opening(connect, manager, resource):
    options = {
        'baud_rate': 115200,
        'encoding': 'UTF-8',
        'read_termination': 'x',
        'write_termination': '\n',
        'end_output': constants.SerialTermination.termination_char,
        'timeout': 5000
    }
    with pytest.warns(
        UserWarning,
        match='baud_rate.*encoding.*end_output.*read_termination.*write_termination'
    ):
        connect(**options)
    manager.open_resource.assert_called_once_with('serial-alias', timeout=5000)
    assert options['baud_rate'] == 115200
    assert resource.baud_rate == 9600
    assert resource.encoding == 'ASCII'
    assert resource.read_termination == ' ok\r\n'
    assert resource.write_termination == '\r'
    assert resource.end_output == constants.SerialTermination.none
    assert resource.timeout == 5000


def test_pyvisa_option_errors_are_propagated_without_driver_cleanup(
    connect,
    manager,
    resource,
    unconnected_driver
):
    error = ValueError('PyVISA rejected timeuot')
    manager.open_resource.side_effect = error
    with pytest.raises(ValueError) as raised:
        connect(timeuot=1000)
    assert raised.value is error
    manager.open_resource.assert_called_once_with('serial-alias', timeuot=1000)
    assert resource.close_count == 0
    assert unconnected_driver._instr is None


def test_resource_class_override_cannot_bypass_fixed_serial_configuration(
    connect,
    manager,
    resource,
    unconnected_driver
):
    with pytest.warns(UserWarning, match='resource_pyclass'):
        connect(resource_pyclass=FakeMessage)
    manager.open_resource.assert_called_once_with('serial-alias')
    assert unconnected_driver._instr is resource
    assert resource.baud_rate == 9600


def test_writable_interface_specific_attribute_is_supported(connect, resource):
    connect(discard_null=True)
    assert resource.discard_null


def test_message_resource_does_not_receive_serial_settings(unconnected_driver):
    resource = FakeMessage()
    manager = make_manager(resource)
    unconnected_driver.connect('serial-alias', resource_manager=manager, send_end=False)
    assert not resource.send_end
    assert resource.commands == ['NO-ECHO']
    assert constants.VI_ATTR_ASRL_BAUD not in resource.values


def test_all_resource_options_are_forwarded_to_pyvisa(connect, manager, resource):
    connect(access_mode=constants.AccessModes.exclusive_lock, open_timeout=2000, timeout=3000)
    manager.open_resource.assert_called_once_with(
        'serial-alias',
        access_mode=constants.AccessModes.exclusive_lock,
        open_timeout=2000,
        timeout=3000
    )
    assert resource.timeout == 3000


def test_default_manager_opens_resource_but_is_not_closed(manager, unconnected_driver):
    with patch('pyvisa.ResourceManager', return_value=manager):
        unconnected_driver.connect('ASRL2::INSTR')
    manager.open_resource.assert_called_once_with('ASRL2::INSTR')
    unconnected_driver.disconnect()
    manager.close.assert_not_called()


def test_reconnecting_requires_disconnect_and_does_not_replace_session(
    connect,
    manager,
    resource,
    unconnected_driver
):
    connect()
    with pytest.raises(RuntimeError, match='Already connected'):
        connect()
    manager.open_resource.assert_called_once()
    assert resource.close_count == 0
    unconnected_driver.disconnect()
    connect()
    assert manager.open_resource.call_count == 2


def test_disconnect_is_idempotent_and_does_not_close_shared_manager(
    connect,
    manager,
    resource,
    unconnected_driver
):
    unconnected_driver.disconnect()
    connect()
    unconnected_driver.disconnect()
    unconnected_driver.disconnect()
    assert resource.close_count == 1
    assert unconnected_driver._instr is None
    manager.close.assert_not_called()


def test_disconnect_clears_state_even_when_close_fails(connect, resource, unconnected_driver):
    connect()
    resource.fail_close = True
    with pytest.raises(OSError):
        unconnected_driver.disconnect()
    assert unconnected_driver._instr is None
    unconnected_driver.disconnect()


def test_open_failure_leaves_device_disconnected(connect, manager, unconnected_driver):
    manager.open_resource.side_effect = OSError('open failed')
    with pytest.raises(OSError, match='open failed'):
        connect()
    assert unconnected_driver._instr is None
    manager.close.assert_not_called()


def test_option_value_failure_inside_open_resource_leaves_driver_disconnected(
    connect,
    manager,
    resource,
    unconnected_driver
):
    resource.fail_attribute = constants.ResourceAttribute.timeout_value
    with pytest.raises(ValueError, match='attribute rejected'):
        connect(timeout=2000)
    assert resource.close_count == 0
    assert unconnected_driver._instr is None
    manager.close.assert_not_called()


def test_fixed_serial_attribute_failure_closes_partial_connection(connect, resource):
    resource.fail_attribute = constants.VI_ATTR_ASRL_BAUD
    with pytest.raises(ValueError):
        connect()
    assert resource.close_count == 1
    assert resource.commands == []


def test_initialization_failure_allows_retry(connect, resource, unconnected_driver):
    resource.fail_command = 'NO-ECHO'
    with pytest.raises(TimeoutError):
        connect()
    assert resource.close_count == 1
    assert unconnected_driver._instr is None
    resource.fail_command = None
    connect()


def test_cleanup_failure_does_not_mask_initialization_failure(
    caplog,
    connect,
    resource,
    unconnected_driver
):
    resource.fail_command = 'NO-ECHO'
    resource.fail_close = True
    with caplog.at_level('WARNING', logger='sp2150.sp2150'), pytest.raises(TimeoutError):
        connect()
    assert unconnected_driver._instr is None
    assert 'Failed to close the instrument after an error' in caplog.text
    assert caplog.records[-1].exc_info is not None


def test_context_cleanup_preserves_body_exception(caplog, connect, resource, unconnected_driver):
    connect()
    resource.fail_close = True
    with caplog.at_level(
        'WARNING',
        logger='sp2150.sp2150'
    ), pytest.raises(
        ValueError,
        match='body failed'
    ):
        with unconnected_driver:
            raise ValueError('body failed')
    assert unconnected_driver._instr is None
    assert 'Failed to disconnect during exception cleanup' in caplog.text
    assert caplog.records[-1].exc_info is not None


def test_context_cleanup_reports_close_error_when_body_succeeded(
    connect,
    resource,
    unconnected_driver
):
    connect()
    resource.fail_close = True
    with pytest.raises(OSError):
        with unconnected_driver:
            pass


def test_non_message_resource_is_closed_and_rejected(connect, manager, resource):
    resource = Mock(spec=Resource)
    manager.open_resource.return_value = resource
    manager.open_resource.side_effect = None
    with pytest.raises(TypeError, match='message-based'):
        connect()
    resource.close.assert_called_once()


def test_disconnected_operations_raise_clear_error(unconnected_driver):
    with pytest.raises(RuntimeError, match='not connected'):
        _ = unconnected_driver.wavelength
    with pytest.raises(RuntimeError, match='not connected'):
        unconnected_driver.home_filter()


def test_scan_timeout_is_restored_when_scan_fails(connect, resource, unconnected_driver):
    connect()
    resource.fail_command = '532.0 NM'
    with pytest.raises(TimeoutError):
        unconnected_driver.scan_to_wavelength('532')
    assert resource.timeout == 1000


def test_simulator_validates_options_and_reconnection_without_hardware():
    device = virtual_sp2150()
    with patch('pyvisa.ResourceManager') as factory:
        with pytest.warns(UserWarning, match='baud_rate'):
            device.connect('ASRL2::INSTR', baud_rate=9600)
        device.disconnect()
        device.connect('ASRL2::INSTR', timeout=2000)
        with pytest.raises(RuntimeError):
            device.connect('ASRL2::INSTR')
        device.disconnect()
        device.disconnect()
        device.connect('dummy')
        factory.assert_not_called()
    device.scan_to_wavelength('532')
    device.grating = '2'
    assert device.wavelength == 532.0
    assert device.grating == 2


def test_simulator_ignores_backend_options_without_generic_validation():
    device = virtual_sp2150()
    device.connect('GPIB0::14::INSTR', enable_repeat_addressing=True)
    device.disconnect()
    device.connect('ASRL2::INSTR', enable_repeat_addressing=True, future_backend_option=1)
