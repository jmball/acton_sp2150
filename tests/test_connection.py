"""Connection and protocol regressions using VISA classes without a backend."""

import unittest
from unittest.mock import Mock, patch

from pyvisa import constants
from pyvisa.resources import MessageBasedResource, Resource, SerialInstrument

from sp2150 import sp2150
from virtual_sp2150 import sp2150 as virtual_sp2150


class FakeResourceMixin:
    """Exercise real PyVISA attribute descriptors without opening a session."""

    def __init__(self):
        self._session = None
        self.values = {constants.ResourceAttribute.timeout_value: 1000}
        self.commands = []
        self.close_count = 0
        self.fail_attribute = None
        self.fail_command = None
        self.fail_close = False

    def set_visa_attribute(self, name, value):
        if name == self.fail_attribute:
            raise ValueError("attribute rejected")
        self.values[name] = value
        return constants.StatusCode.success

    def get_visa_attribute(self, name):
        return self.values[name]

    def query(self, command):
        self.commands.append(command)
        if command == self.fail_command:
            raise TimeoutError("query failed")
        return {"?NM": " 0.0 nm", "?NM/MIN": " 60.0 nm/min"}.get(command, "")

    def close(self):
        self.close_count += 1
        if self.fail_close:
            raise OSError("close failed")


class FakeSerial(FakeResourceMixin, SerialInstrument):
    pass


class FakeMessage(FakeResourceMixin, MessageBasedResource):
    pass


class ConnectionTests(unittest.TestCase):
    def setUp(self):
        self.resource = FakeSerial()
        self.manager = Mock()
        self.manager.open_resource.return_value = self.resource
        self.device = sp2150()

    def connect(self, **options):
        self.device.connect("serial-alias", resource_manager=self.manager, **options)

    def test_manager_is_keyword_only_in_both_drivers(self):
        for driver in (sp2150, virtual_sp2150):
            with self.subTest(driver=driver), self.assertRaises(TypeError):
                driver().connect("ASRL2::INSTR", self.manager)

    def test_serial_settings_and_protocol_are_applied_before_first_query(self):
        original_query = self.resource.query

        def query(command):
            self.assertEqual(self.resource.baud_rate, 9600)
            self.assertEqual(self.resource.data_bits, 8)
            self.assertEqual(self.resource.parity, constants.Parity.none)
            self.assertEqual(self.resource.stop_bits, constants.StopBits.one)
            self.assertEqual(self.resource.flow_control, constants.ControlFlow.none)
            self.assertEqual(self.resource.end_input, constants.SerialTermination.termination_char)
            self.assertEqual(self.resource.end_output, constants.SerialTermination.none)
            self.assertEqual(self.resource.write_termination, "\r")
            self.assertEqual(self.resource.read_termination, " ok\r\n")
            self.assertEqual(self.resource.encoding, "ASCII")
            return original_query(command)

        self.resource.query = query
        self.connect(timeout=5000, query_delay=0.1, chunk_size=512)
        self.assertEqual(self.resource.commands, ["NO-ECHO"])
        self.assertEqual(self.resource.timeout, 5000)
        self.assertEqual(self.resource.query_delay, 0.1)
        self.assertEqual(self.resource.chunk_size, 512)
        self.assertIs(self.device._resource_manager, self.manager)

    def test_fixed_options_are_rejected_even_when_matching_defaults(self):
        options = {
            "read_termination": " ok\r\n", "write_termination": "\r",
            "encoding": "ASCII", "baud_rate": 9600, "data_bits": 8,
            "parity": constants.Parity.none, "stop_bits": constants.StopBits.one,
            "flow_control": constants.ControlFlow.none,
            "end_input": constants.SerialTermination.termination_char,
            "end_output": constants.SerialTermination.none,
        }
        for name, value in options.items():
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, name):
                self.connect(**{name: value})
        self.manager.open_resource.assert_not_called()
        self.assertIsNone(self.device.instr)

    def test_invalid_names_read_only_attributes_and_methods_are_rejected(self):
        for name in ("timeuot", "bytes_in_buffer", "close", "session", "resource_pyclass", "_session"):
            with self.subTest(name=name), self.assertRaisesRegex(TypeError, name):
                self.connect(**{name: 1})
        self.assertEqual(self.resource.close_count, 6)
        self.assertEqual(self.resource.commands, [])
        self.assertIsNone(self.device.instr)

    def test_writable_interface_specific_attribute_is_supported(self):
        self.connect(discard_null=True)
        self.assertTrue(self.resource.discard_null)

    def test_interface_specific_attribute_is_rejected_for_other_interfaces(self):
        self.manager.open_resource.return_value = resource = FakeMessage()
        with self.assertRaisesRegex(TypeError, "discard_null"):
            self.connect(discard_null=True)
        self.assertEqual(resource.close_count, 1)

    def test_message_resource_does_not_receive_serial_settings(self):
        self.manager.open_resource.return_value = resource = FakeMessage()
        self.connect(send_end=False)
        self.assertFalse(resource.send_end)
        self.assertEqual(resource.commands, ["NO-ECHO"])
        self.assertNotIn(constants.VI_ATTR_ASRL_BAUD, resource.values)

    def test_open_options_are_forwarded_without_resource_attributes(self):
        self.connect(access_mode=constants.AccessModes.exclusive_lock, open_timeout=2000, timeout=3000)
        self.manager.open_resource.assert_called_once_with(
            "serial-alias", access_mode=constants.AccessModes.exclusive_lock, open_timeout=2000
        )
        self.assertEqual(self.resource.timeout, 3000)

    def test_default_manager_is_retained_but_not_closed(self):
        with patch("pyvisa.ResourceManager", return_value=self.manager):
            self.device.connect("ASRL2::INSTR")
        self.assertIs(self.device._resource_manager, self.manager)
        self.device.disconnect()
        self.manager.close.assert_not_called()

    def test_reconnecting_requires_disconnect_and_does_not_replace_session(self):
        self.connect()
        with self.assertRaisesRegex(RuntimeError, "Already connected"):
            self.connect()
        self.manager.open_resource.assert_called_once()
        self.assertEqual(self.resource.close_count, 0)
        self.device.disconnect()
        self.connect()
        self.assertEqual(self.manager.open_resource.call_count, 2)

    def test_disconnect_is_idempotent_and_does_not_close_shared_manager(self):
        self.device.disconnect()
        self.connect()
        self.device.disconnect()
        self.device.disconnect()
        self.assertEqual(self.resource.close_count, 1)
        self.assertIsNone(self.device.instr)
        self.assertIsNone(self.device._resource_manager)
        self.manager.close.assert_not_called()

    def test_disconnect_clears_state_even_when_close_fails(self):
        self.connect()
        self.resource.fail_close = True
        with self.assertRaises(OSError):
            self.device.disconnect()
        self.assertIsNone(self.device.instr)
        self.assertIsNone(self.device._resource_manager)
        self.device.disconnect()

    def test_open_failure_leaves_device_disconnected(self):
        self.manager.open_resource.side_effect = OSError("open failed")
        with self.assertRaisesRegex(OSError, "open failed"):
            self.connect()
        self.assertIsNone(self.device.instr)
        self.assertIsNone(self.device._resource_manager)
        self.manager.close.assert_not_called()

    def test_attribute_failure_closes_partial_connection(self):
        self.resource.fail_attribute = constants.ResourceAttribute.timeout_value
        with self.assertRaisesRegex(ValueError, "attribute rejected"):
            self.connect(timeout=2000)
        self.assertEqual(self.resource.close_count, 1)
        self.assertIsNone(self.device.instr)
        self.assertIsNone(self.device._resource_manager)
        self.manager.close.assert_not_called()

    def test_fixed_serial_attribute_failure_closes_partial_connection(self):
        self.resource.fail_attribute = constants.VI_ATTR_ASRL_BAUD
        with self.assertRaises(ValueError):
            self.connect()
        self.assertEqual(self.resource.close_count, 1)
        self.assertEqual(self.resource.commands, [])

    def test_initialization_failure_allows_retry(self):
        self.resource.fail_command = "NO-ECHO"
        with self.assertRaises(TimeoutError):
            self.connect()
        self.assertEqual(self.resource.close_count, 1)
        self.assertIsNone(self.device.instr)
        self.resource.fail_command = None
        self.connect()

    def test_cleanup_failure_does_not_mask_initialization_failure(self):
        self.resource.fail_command = "NO-ECHO"
        self.resource.fail_close = True
        with self.assertLogs("sp2150.sp2150", level="WARNING"), self.assertRaises(TimeoutError):
            self.connect()
        self.assertIsNone(self.device.instr)

    def test_context_cleanup_preserves_body_exception(self):
        self.connect()
        self.resource.fail_close = True
        with self.assertLogs("sp2150.sp2150", level="WARNING"), self.assertRaisesRegex(ValueError, "body failed"):
            with self.device:
                raise ValueError("body failed")
        self.assertIsNone(self.device.instr)

    def test_context_cleanup_reports_close_error_when_body_succeeded(self):
        self.connect()
        self.resource.fail_close = True
        with self.assertRaises(OSError):
            with self.device:
                pass

    def test_non_message_resource_is_closed_and_rejected(self):
        resource = Mock(spec=Resource)
        self.manager.open_resource.return_value = resource
        with self.assertRaisesRegex(TypeError, "message-based"):
            self.connect()
        resource.close.assert_called_once()

    def test_disconnected_operations_raise_clear_error(self):
        with self.assertRaisesRegex(RuntimeError, "not connected"):
            _ = self.device.wavelength
        with self.assertRaisesRegex(RuntimeError, "not connected"):
            self.device.home_filter()

    def test_scan_timeout_is_restored_when_scan_fails(self):
        self.connect()
        self.resource.fail_command = "532.0 NM"
        with self.assertRaises(TimeoutError):
            self.device.scan_to_wavelength("532")
        self.assertEqual(self.resource.timeout, 1000)

    def test_simulator_validates_options_and_reconnection_without_hardware(self):
        device = virtual_sp2150()
        with patch("pyvisa.ResourceManager") as factory:
            with self.assertRaises(ValueError):
                device.connect("ASRL2::INSTR", baud_rate=9600)
            with self.assertRaises(TypeError):
                device.connect("ASRL2::INSTR", timeuot=2000)
            device.connect("ASRL2::INSTR", timeout=2000)
            with self.assertRaises(RuntimeError):
                device.connect("ASRL2::INSTR")
            device.disconnect()
            device.disconnect()
            device.connect("dummy")
            factory.assert_not_called()
        device.scan_to_wavelength("532")
        device.grating = "2"
        self.assertEqual(device.wavelength, 532.0)
        self.assertEqual(device.grating, 2)

    def test_simulator_accepts_gpib_specific_writable_options(self):
        device = virtual_sp2150()
        device.connect("GPIB0::14::INSTR", enable_repeat_addressing=True)
        device.disconnect()
        with self.assertRaises(TypeError):
            device.connect("ASRL2::INSTR", enable_repeat_addressing=True)


if __name__ == "__main__":
    unittest.main()
