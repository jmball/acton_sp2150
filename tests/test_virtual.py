"""Simulator state and lifecycle needed by simulated experiments."""

import unittest
from unittest.mock import patch

from virtual_sp2150 import sp2150


class SimulatorTests(unittest.TestCase):
    def setUp(self):
        self.device = sp2150()
        self.device.connect("virtual")
        self.addCleanup(self.device.disconnect)

    def test_initial_state(self):
        self.assertEqual(self.device.scan_speed, 1000.0)
        self.assertEqual(self.device.wavelength, 0.0)
        self.assertEqual(self.device.grating, 1)
        self.assertEqual(self.device.turret, 1)
        self.assertEqual(self.device.filter, 1)

    def test_instances_are_independent(self):
        with sp2150() as other:
            other.connect("virtual")
            self.device.wavelength = 532
            self.device.filter = 3
            self.assertEqual(other.wavelength, 0.0)
            self.assertEqual(other.filter, 1)

    def test_reconnect_preserves_instrument_state(self):
        self.device.wavelength = 532
        self.device.grating = 2
        self.device.disconnect()
        self.device.connect("virtual")
        self.assertEqual(self.device.wavelength, 532.0)
        self.assertEqual(self.device.grating, 2)

    def test_context_manager_disconnects_on_exception(self):
        with self.assertRaisesRegex(ValueError, "experiment failed"):
            with self.device as entered:
                self.assertIs(entered, self.device)
                raise ValueError("experiment failed")
        with self.assertRaises(RuntimeError):
            _ = self.device.wavelength

    def test_one_decimal_precision_matches_driver_commands(self):
        self.device.wavelength = "532.26"
        self.device.scan_speed = "123.46"
        self.assertEqual(self.device.wavelength, 532.3)
        self.assertEqual(self.device.scan_speed, 123.5)
        self.device.scan_to_wavelength("533.26")
        self.assertEqual(self.device.wavelength, 533.3)

    def test_invalid_numeric_values_preserve_previous_state(self):
        for name in ("wavelength", "scan_speed", "grating", "turret", "filter"):
            original = getattr(self.device, name)
            with self.subTest(name=name), self.assertRaises(ValueError):
                setattr(self.device, name, "not-a-number")
            self.assertEqual(getattr(self.device, name), original)

    def test_simulated_experiment_never_constructs_a_resource_manager(self):
        with patch("pyvisa.ResourceManager") as manager:
            with sp2150() as device:
                device.connect("ASRL2::INSTR", timeout=30000)
                device.grating = 2
                device.filter = 3
                readings = []
                for wavelength in (500, 501, 502):
                    device.scan_to_wavelength(wavelength)
                    readings.append(device.wavelength)
            self.assertEqual(readings, [500.0, 501.0, 502.0])
            manager.assert_not_called()
