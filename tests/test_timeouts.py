"""Check operation-specific timeouts while commands execute and after failures."""

import math
import unittest
from unittest.mock import patch

from pyvisa import constants

from sp2150 import sp2150
from virtual_sp2150 import sp2150 as virtual_sp2150
from tests.fakes import FakeSerial, make_manager


class OperationTimeoutTests(unittest.TestCase):
    def setUp(self):
        self.resource = FakeSerial()
        self.device = sp2150()
        self.device.connect("fake", resource_manager=make_manager(self.resource))
        self.addCleanup(self.device.disconnect)
        self.observed = []
        original_query = self.resource.query

        def query(command):
            self.observed.append((command, self.resource.timeout))
            return original_query(command)

        self.resource.query = query

    def test_defaults_match_simulator_and_instances_are_independent(self):
        simulated = virtual_sp2150()
        for name, value in (("grating_timeout_ms", 30000), ("filter_timeout_ms", 10000),
                            ("filter_home_timeout_ms", 20000), ("scan_timeout_buffer_ms", 5000)):
            with self.subTest(name=name):
                self.assertEqual(getattr(self.device, name), value)
                self.assertEqual(getattr(simulated, name), value)
                setattr(self.device, name, value + 1)
                self.assertEqual(getattr(simulated, name), value)

    def test_fixed_operations_extend_and_restore_timeout(self):
        self.device.grating = 2
        self.device.filter = 3
        self.device.home_filter()
        self.assertEqual(self.observed, [("2 GRATING", 30000), ("3 FILTER", 10000), ("FHOME", 20000)])
        self.assertEqual(self.resource.timeout, 1000)

    def test_custom_operation_allowances_are_used(self):
        self.device.grating_timeout_ms = 41000
        self.device.filter_timeout_ms = 12000
        self.device.filter_home_timeout_ms = 25000
        self.device.grating = 2
        self.device.filter = 3
        self.device.home_filter()
        self.assertEqual(self.observed, [("2 GRATING", 41000), ("3 FILTER", 12000), ("FHOME", 25000)])
        self.assertEqual(self.resource.timeout, 1000)

    def test_fixed_operations_restore_timeout_after_command_failure(self):
        for command, operation in (
            ("2 GRATING", lambda: setattr(self.device, "grating", 2)),
            ("3 FILTER", lambda: setattr(self.device, "filter", 3)),
            ("FHOME", self.device.home_filter),
        ):
            with self.subTest(command=command):
                self.resource.fail_command = command
                with self.assertRaises(TimeoutError):
                    operation()
                self.assertEqual(self.resource.timeout, 1000)

    def test_longer_and_infinite_caller_timeouts_are_preserved(self):
        for timeout in (60000, None):
            with self.subTest(timeout=timeout):
                self.resource.timeout = timeout
                old_timeout = self.resource.timeout
                with patch.object(self.resource, "set_visa_attribute", wraps=self.resource.set_visa_attribute) as setter:
                    self.device.grating = 2
                    self.device.filter = 3
                    self.device.home_filter()
                    self.device.scan_to_wavelength(1)
                    setter.assert_not_called()
                self.assertEqual(self.resource.timeout, old_timeout)
                self.assertTrue(all(value == old_timeout for _, value in self.observed))
                self.observed.clear()

    def test_scan_uses_duration_plus_custom_buffer_even_when_duration_is_short(self):
        self.resource.scan_speed = 600
        self.device.scan_timeout_buffer_ms = 1500
        self.device.scan_to_wavelength(1)
        self.assertEqual(self.observed, [("?NM", 1000), ("?NM/MIN", 1000), ("1.0 NM", 1600)])
        self.assertEqual(self.resource.timeout, 1000)

    def test_scan_buffer_can_be_zero(self):
        self.device.scan_timeout_buffer_ms = 0
        self.device.scan_to_wavelength(100)
        self.assertEqual(self.observed[-1], ("100.0 NM", 6000))
        self.assertEqual(self.resource.timeout, 1000)

    def test_scan_duration_uses_the_wavelength_sent_to_hardware(self):
        self.resource.scan_speed = 600
        self.device.scan_timeout_buffer_ms = 0
        self.resource.timeout = 1
        self.device.scan_to_wavelength(0.06)
        self.assertEqual(self.observed[-1], ("0.1 NM", 10))
        self.assertEqual(self.resource.timeout, 1)

    def test_invalid_buffer_is_rejected_before_io(self):
        for buffer in (-1, math.inf, math.nan):
            with self.subTest(buffer=buffer):
                self.device.scan_timeout_buffer_ms = buffer
                with self.assertRaises(ValueError):
                    self.device.scan_to_wavelength(100)
                self.assertEqual(self.observed, [])
                self.assertEqual(self.resource.timeout, 1000)

    def test_initial_timeout_assignment_failure_sends_no_command(self):
        self.resource.fail_attribute = constants.ResourceAttribute.timeout_value
        with self.assertRaisesRegex(ValueError, "attribute rejected"):
            self.device.grating = 2
        self.assertEqual(self.observed, [])
        self.assertEqual(self.resource.timeout, 1000)

    def test_restoration_failure_preserves_active_command_error(self):
        original_query = self.resource.query

        def query(command):
            if command == "2 GRATING":
                self.resource.fail_attribute = constants.ResourceAttribute.timeout_value
                raise TimeoutError("original command error")
            return original_query(command)

        self.resource.query = query
        with self.assertLogs("sp2150.sp2150", level="WARNING"), self.assertRaisesRegex(TimeoutError, "original command error"):
            self.device.grating = 2

    def test_restoration_failure_is_raised_when_command_succeeds(self):
        original_query = self.resource.query

        def query(command):
            result = original_query(command)
            self.resource.fail_attribute = constants.ResourceAttribute.timeout_value
            return result

        self.resource.query = query
        with self.assertRaisesRegex(ValueError, "attribute rejected"):
            self.device.grating = 2
        self.assertEqual(self.resource.grating, 2)
