"""Reject invalid numeric commands before changing instrument state."""

import unittest

from sp2150 import sp2150
from virtual_sp2150 import sp2150 as virtual_sp2150
from tests.fakes import FakeSerial, make_manager


class NumericValidationTests(unittest.TestCase):
    def setUp(self):
        self.resource = FakeSerial()
        actual = sp2150()
        actual.connect("fake", resource_manager=make_manager(self.resource))
        simulated = virtual_sp2150()
        simulated.connect("virtual")
        self.devices = (actual, simulated)
        for device in self.devices:
            self.addCleanup(device.disconnect)

    def test_invalid_scan_speed_preserves_state_and_sends_no_command(self):
        for device in self.devices:
            original = device.scan_speed
            for value in (0, -1, -0.01, 0.01, 0.049, "0", "0.01", "bad",
                          float("nan"), float("inf"), float("-inf"), "nan", "inf"):
                with self.subTest(driver=type(device), value=value):
                    previous_commands = self.resource.commands.copy()
                    with self.assertRaises(ValueError):
                        device.scan_speed = value
                    self.assertEqual(self.resource.commands, previous_commands)
                    self.assertEqual(device.scan_speed, original)

    def test_nonfinite_wavelengths_and_scan_targets_send_no_commands(self):
        for device in self.devices:
            original = device.wavelength
            for value in (float("nan"), float("inf"), float("-inf"), "nan", "inf", "-inf", "bad"):
                for operation in ("goto", "scan"):
                    with self.subTest(driver=type(device), value=value, operation=operation):
                        previous_commands = self.resource.commands.copy()
                        with self.assertRaises(ValueError):
                            if operation == "goto":
                                device.wavelength = value
                            else:
                                device.scan_to_wavelength(value)
                        self.assertEqual(self.resource.commands, previous_commands)
                        self.assertEqual(device.wavelength, original)

    def test_valid_values_retain_device_precision(self):
        for device in self.devices:
            for value, expected in (("0.06", 0.1), (123.46, 123.5)):
                with self.subTest(driver=type(device), value=value):
                    device.scan_speed = value
                    self.assertEqual(device.scan_speed, expected)
            device.wavelength = "532.26"
            self.assertEqual(device.wavelength, 532.3)
            device.scan_to_wavelength("0")
            self.assertEqual(device.wavelength, 0.0)

    def test_invalid_reported_scan_speed_stops_before_scan_or_timeout_change(self):
        device = self.devices[0]
        for speed in (0, -1, float("nan"), float("inf"), float("-inf")):
            with self.subTest(speed=speed):
                self.resource.scan_speed = speed
                self.resource.commands.clear()
                old_timeout = self.resource.timeout
                with self.assertRaisesRegex(ValueError, "Reported scan speed"):
                    device.scan_to_wavelength(500)
                self.assertEqual(self.resource.commands, ["?NM", "?NM/MIN"])
                self.assertEqual(self.resource.timeout, old_timeout)
                self.assertEqual(self.resource.wavelength, 0.0)
