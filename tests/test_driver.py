"""Fake-backed driver connections, wire protocol, parsing, and timeouts."""

import math
from unittest.mock import Mock, patch

import pytest
from pyvisa import constants
from pyvisa.resources import Resource

from tests.fakes import FakeMessage, make_manager


@pytest.fixture
def observed(connected_driver, resource):
    observations = []
    original_query = resource.query

    def query(command):
        observations.append((command, resource.timeout))
        return original_query(command)

    resource.query = query
    return observations


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
        assert resource.write_termination == "\r"
        assert resource.read_termination == " ok\r\n"
        assert resource.encoding == "ASCII"
        return original_query(command)

    resource.query = query
    connect(timeout=5000, query_delay=0.1, chunk_size=512)
    assert resource.commands == ["NO-ECHO"]
    assert resource.timeout == 5000
    assert resource.query_delay == 0.1
    assert resource.chunk_size == 512


def test_conflicting_fixed_options_are_removed_before_opening(
    connect, manager, resource
):
    options = {
        "baud_rate": 115200,
        "encoding": "UTF-8",
        "read_termination": "x",
        "write_termination": "\n",
        "end_output": constants.SerialTermination.termination_char,
        "timeout": 5000,
    }
    with pytest.warns(
        UserWarning,
        match="baud_rate.*encoding.*end_output.*read_termination.*write_termination",
    ):
        connect(**options)
    manager.open_resource.assert_called_once_with("serial-alias", timeout=5000)
    assert options["baud_rate"] == 115200
    assert resource.baud_rate == 9600
    assert resource.encoding == "ASCII"
    assert resource.read_termination == " ok\r\n"
    assert resource.write_termination == "\r"
    assert resource.end_output == constants.SerialTermination.none
    assert resource.timeout == 5000


def test_pyvisa_option_errors_are_propagated_without_driver_cleanup(
    connect, manager, resource, unconnected_driver
):
    error = ValueError("PyVISA rejected timeuot")
    manager.open_resource.side_effect = error
    with pytest.raises(ValueError) as raised:
        connect(timeuot=1000)
    assert raised.value is error
    manager.open_resource.assert_called_once_with("serial-alias", timeuot=1000)
    assert resource.close_count == 0
    assert unconnected_driver._instr is None


def test_resource_class_override_cannot_bypass_fixed_serial_configuration(
    connect, manager, resource, unconnected_driver
):
    with pytest.warns(UserWarning, match="resource_pyclass"):
        connect(resource_pyclass=FakeMessage)
    manager.open_resource.assert_called_once_with("serial-alias")
    assert unconnected_driver._instr is resource
    assert resource.baud_rate == 9600


def test_writable_interface_specific_attribute_is_supported(connect, resource):
    connect(discard_null=True)
    assert resource.discard_null


def test_message_resource_does_not_receive_serial_settings(unconnected_driver):
    resource = FakeMessage()
    manager = make_manager(resource)
    unconnected_driver.connect("serial-alias", resource_manager=manager, send_end=False)
    assert not resource.send_end
    assert resource.commands == ["NO-ECHO"]
    assert constants.VI_ATTR_ASRL_BAUD not in resource.values


def test_all_resource_options_are_forwarded_to_pyvisa(connect, manager, resource):
    connect(
        access_mode=constants.AccessModes.exclusive_lock,
        open_timeout=2000,
        timeout=3000,
    )
    manager.open_resource.assert_called_once_with(
        "serial-alias",
        access_mode=constants.AccessModes.exclusive_lock,
        open_timeout=2000,
        timeout=3000,
    )
    assert resource.timeout == 3000


def test_default_manager_opens_resource_but_is_not_closed(manager, unconnected_driver):
    with patch("pyvisa.ResourceManager", return_value=manager):
        unconnected_driver.connect("ASRL2::INSTR")
    manager.open_resource.assert_called_once_with("ASRL2::INSTR")
    unconnected_driver.disconnect()
    manager.close.assert_not_called()


def test_reconnecting_requires_disconnect_and_does_not_replace_session(
    connect, manager, resource, unconnected_driver
):
    connect()
    with pytest.raises(RuntimeError, match="Already connected"):
        connect()
    manager.open_resource.assert_called_once()
    assert resource.close_count == 0
    unconnected_driver.disconnect()
    connect()
    assert manager.open_resource.call_count == 2


def test_disconnect_is_idempotent_and_does_not_close_shared_manager(
    connect, manager, resource, unconnected_driver
):
    unconnected_driver.disconnect()
    connect()
    unconnected_driver.disconnect()
    unconnected_driver.disconnect()
    assert resource.close_count == 1
    assert unconnected_driver._instr is None
    manager.close.assert_not_called()


def test_disconnect_clears_state_even_when_close_fails(
    connect, resource, unconnected_driver
):
    connect()
    resource.fail_close = True
    with pytest.raises(OSError):
        unconnected_driver.disconnect()
    assert unconnected_driver._instr is None
    unconnected_driver.disconnect()


def test_open_failure_leaves_device_disconnected(connect, manager, unconnected_driver):
    manager.open_resource.side_effect = OSError("open failed")
    with pytest.raises(OSError, match="open failed"):
        connect()
    assert unconnected_driver._instr is None
    manager.close.assert_not_called()


def test_option_value_failure_inside_open_resource_leaves_driver_disconnected(
    connect, manager, resource, unconnected_driver
):
    resource.fail_attribute = constants.ResourceAttribute.timeout_value
    with pytest.raises(ValueError, match="attribute rejected"):
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
    resource.fail_command = "NO-ECHO"
    with pytest.raises(TimeoutError):
        connect()
    assert resource.close_count == 1
    assert unconnected_driver._instr is None
    resource.fail_command = None
    connect()


def test_cleanup_failure_does_not_mask_initialization_failure(
    caplog, connect, resource, unconnected_driver
):
    resource.fail_command = "NO-ECHO"
    resource.fail_close = True
    with (
        caplog.at_level("WARNING", logger="sp2150.sp2150"),
        pytest.raises(TimeoutError),
    ):
        connect()
    assert unconnected_driver._instr is None
    assert "Failed to close the instrument after an error" in caplog.text
    assert caplog.records[-1].exc_info is not None


def test_context_cleanup_preserves_body_exception(
    caplog, connect, resource, unconnected_driver
):
    connect()
    resource.fail_close = True
    with (
        caplog.at_level("WARNING", logger="sp2150.sp2150"),
        pytest.raises(ValueError, match="body failed"),
    ):
        with unconnected_driver:
            raise ValueError("body failed")
    assert unconnected_driver._instr is None
    assert "Failed to disconnect during exception cleanup" in caplog.text
    assert caplog.records[-1].exc_info is not None


def test_context_cleanup_reports_close_error_when_body_succeeded(
    connect, resource, unconnected_driver
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
    with pytest.raises(TypeError, match="message-based"):
        connect()
    resource.close.assert_called_once()


def test_scan_timeout_is_restored_when_scan_fails(
    connect, resource, unconnected_driver
):
    connect()
    resource.fail_command = "532.0 NM"
    with pytest.raises(TimeoutError):
        unconnected_driver.scan_to_wavelength("532")
    assert resource.timeout == 1000


@pytest.mark.parametrize(
    "name,command",
    list(
        {
            "scan_speed": "?NM/MIN",
            "wavelength": "?NM",
            "grating": "?GRATING",
            "turret": "?TURRET",
            "filter": "?FILTER",
        }.items()
    ),
)
def test_property_getter_commands(connected_driver, resource, name, command):
    getattr(connected_driver, name)
    assert resource.commands.pop() == command


@pytest.mark.parametrize(
    "name,value,command",
    (
        ("scan_speed", "123.46", "123.5 NM/MIN"),
        ("wavelength", "532.26", "532.3 GOTO"),
        ("grating", "2", "2 GRATING"),
        ("turret", "1", "1 TURRET"),
        ("filter", "3", "3 FILTER"),
    ),
)
def test_property_setter_commands(connected_driver, resource, name, value, command):
    setattr(connected_driver, name, value)
    assert resource.commands.pop() == command


def test_scan_command_and_readback(connected_driver, resource):
    connected_driver.scan_to_wavelength("532.26")
    assert resource.commands == ["?NM", "?NM/MIN", "532.3 NM"]
    assert connected_driver.wavelength == 532.3


def test_home_command(connected_driver, resource):
    connected_driver.home_filter()
    assert resource.commands == ["FHOME"]


def test_query_preserves_response_while_property_parses_value(connected_driver):
    assert connected_driver._query("?NM/MIN") == " 1000.0 nm/min"
    assert connected_driver.scan_speed == 1000.0


@pytest.mark.parametrize(
    "method,argument", (("_write", "?TURRETS"), ("_query", "FHOME"), ("_read_bytes", 1))
)
def test_disconnected_communication_does_not_reach_resource(
    connected_driver, resource, method, argument
):
    connected_driver.disconnect()
    with pytest.raises(RuntimeError, match="not connected"):
        getattr(connected_driver, method)(argument)
    assert resource.commands == []
    assert resource._pending == b""


@pytest.mark.parametrize(
    "name,command", (("grating_info", "?GRATINGS"), ("turret_info", "?TURRETS"))
)
def test_information_commands_preserve_internal_newlines_and_trailing_letters(
    connected_driver, resource, name, command
):
    assert getattr(connected_driver, name) == getattr(resource, name)
    assert resource.commands.pop() == command
    assert resource._pending == b""


def test_incomplete_information_response_propagates_timeout(connected_driver, resource):
    original_write = resource.write

    def incomplete_write(command):
        original_write(command)
        resource._pending = b" partial response\r\n"

    resource.write = incomplete_write
    with pytest.raises(TimeoutError):
        _ = connected_driver.turret_info


def test_fixed_operations_extend_and_restore_timeout(
    connected_driver, observed, resource
):
    connected_driver.grating = 2
    connected_driver.filter = 3
    connected_driver.home_filter()
    assert observed == [("2 GRATING", 30000), ("3 FILTER", 10000), ("FHOME", 20000)]
    assert resource.timeout == 1000


def test_custom_operation_allowances_are_used(connected_driver, observed, resource):
    connected_driver.grating_timeout_ms = 41000
    connected_driver.filter_timeout_ms = 12000
    connected_driver.filter_home_timeout_ms = 25000
    connected_driver.grating = 2
    connected_driver.filter = 3
    connected_driver.home_filter()
    assert observed == [("2 GRATING", 41000), ("3 FILTER", 12000), ("FHOME", 25000)]
    assert resource.timeout == 1000


def test_fixed_operations_restore_timeout_after_command_failure(
    connected_driver, resource
):
    for command, operation in (
        ("2 GRATING", lambda: setattr(connected_driver, "grating", 2)),
        ("3 FILTER", lambda: setattr(connected_driver, "filter", 3)),
        ("FHOME", connected_driver.home_filter),
    ):
        resource.fail_command = command
        with pytest.raises(TimeoutError):
            operation()
        assert resource.timeout == 1000


@pytest.mark.parametrize("timeout", (60000, None))
def test_longer_and_infinite_caller_timeouts_are_preserved(
    connected_driver, observed, resource, timeout
):
    resource.timeout = timeout
    old_timeout = resource.timeout
    with patch.object(
        resource, "set_visa_attribute", wraps=resource.set_visa_attribute
    ) as setter:
        connected_driver.grating = 2
        connected_driver.filter = 3
        connected_driver.home_filter()
        connected_driver.scan_to_wavelength(1)
        setter.assert_not_called()
    assert resource.timeout == old_timeout
    assert all((value == old_timeout for _, value in observed))
    observed.clear()


def test_scan_uses_duration_plus_custom_buffer_even_when_duration_is_short(
    connected_driver, observed, resource
):
    resource.scan_speed = 600
    connected_driver.scan_timeout_buffer_ms = 1500
    connected_driver.scan_to_wavelength(1)
    assert observed == [("?NM", 1000), ("?NM/MIN", 1000), ("1.0 NM", 1600)]
    assert resource.timeout == 1000


def test_scan_buffer_can_be_zero(connected_driver, observed, resource):
    connected_driver.scan_timeout_buffer_ms = 0
    connected_driver.scan_to_wavelength(100)
    assert observed[-1] == ("100.0 NM", 6000)
    assert resource.timeout == 1000


def test_scan_duration_uses_the_wavelength_sent_to_hardware(
    connected_driver, observed, resource
):
    resource.scan_speed = 600
    connected_driver.scan_timeout_buffer_ms = 0
    resource.timeout = 1
    connected_driver.scan_to_wavelength(0.06)
    assert observed[-1] == ("0.1 NM", 10)
    assert resource.timeout == 1


@pytest.mark.parametrize("buffer", (-1, math.inf, math.nan))
def test_invalid_buffer_is_rejected_before_io(
    connected_driver, observed, resource, buffer
):
    connected_driver.scan_timeout_buffer_ms = buffer
    with pytest.raises(ValueError):
        connected_driver.scan_to_wavelength(100)
    assert observed == []
    assert resource.timeout == 1000


def test_initial_timeout_assignment_failure_sends_no_command(
    connected_driver, observed, resource
):
    resource.fail_attribute = constants.ResourceAttribute.timeout_value
    with pytest.raises(ValueError, match="attribute rejected"):
        connected_driver.grating = 2
    assert observed == []
    assert resource.timeout == 1000


def test_restoration_failure_preserves_active_command_error(
    caplog, connected_driver, resource
):
    original_query = resource.query

    def query(command):
        if command == "2 GRATING":
            resource.fail_attribute = constants.ResourceAttribute.timeout_value
            raise TimeoutError("original command error")
        return original_query(command)

    resource.query = query
    with (
        caplog.at_level("WARNING", logger="sp2150.sp2150"),
        pytest.raises(TimeoutError, match="original command error"),
    ):
        connected_driver.grating = 2
    assert "Failed to restore the instrument timeout after an error" in caplog.text
    assert caplog.records[-1].exc_info is not None


def test_restoration_failure_is_raised_when_command_succeeds(
    connected_driver, resource
):
    original_query = resource.query

    def query(command):
        result = original_query(command)
        resource.fail_attribute = constants.ResourceAttribute.timeout_value
        return result

    resource.query = query
    with pytest.raises(ValueError, match="attribute rejected"):
        connected_driver.grating = 2
    assert resource.grating == 2


@pytest.mark.parametrize(
    "speed,expected_message",
    [
        (0, "Reported scan speed must be positive"),
        (-1, "Reported scan speed must be positive"),
        (float("nan"), "Value must be finite"),
        (float("inf"), "Value must be finite"),
        (float("-inf"), "Value must be finite"),
    ],
)
def test_invalid_reported_scan_speed_stops_before_scan_or_timeout_change(
    connected_driver, resource, speed, expected_message
):
    resource.scan_speed = speed
    resource.commands.clear()
    old_timeout = resource.timeout
    with pytest.raises(ValueError, match=expected_message):
        connected_driver.scan_to_wavelength(500)
    assert resource.commands == ["?NM", "?NM/MIN"]
    assert resource.timeout == old_timeout
    assert resource.wavelength == 0.0
