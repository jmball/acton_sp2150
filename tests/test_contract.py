"""Enforce public API and experiment behavior parity without hardware."""

import inspect
import unittest
from unittest.mock import Mock

from sp2150 import sp2150
from virtual_sp2150 import sp2150 as virtual_sp2150

from tests.contract import InstrumentContract
from tests.fakes import FakeSerial


class SimulatorContract(InstrumentContract, unittest.TestCase):
    def setUp(self):
        self.device = virtual_sp2150()
        self.device.connect("ASRL2::INSTR")
        self.addCleanup(self.device.disconnect)


class DriverContract(InstrumentContract, unittest.TestCase):
    def setUp(self):
        self.resource = FakeSerial()
        self.manager = Mock()
        self.manager.open_resource.return_value = self.resource
        self.device = sp2150()
        self.device.connect("ASRL2::INSTR", resource_manager=self.manager)
        self.addCleanup(self.device.disconnect)


class InterfaceParity(unittest.TestCase):
    def test_public_members_and_signatures_match(self):
        def public_members(driver):
            return {
                name: member for name, member in inspect.getmembers(driver)
                if not name.startswith("_")
                and (inspect.isfunction(member) or isinstance(member, property))
            }

        actual = public_members(sp2150)
        simulated = public_members(virtual_sp2150)
        self.assertEqual(actual.keys(), simulated.keys())
        for name, member in actual.items():
            with self.subTest(name=name):
                other = simulated[name]
                if isinstance(member, property):
                    self.assertIsInstance(other, property)
                    for accessor in ("fget", "fset", "fdel"):
                        first, second = getattr(member, accessor), getattr(other, accessor)
                        self.assertEqual(first is None, second is None)
                        if first is not None:
                            self.assertEqual(inspect.signature(first), inspect.signature(second))
                else:
                    self.assertEqual(inspect.signature(member), inspect.signature(other))

    def test_context_manager_signatures_match(self):
        for name in ("__init__", "__enter__", "__exit__"):
            with self.subTest(name=name):
                self.assertEqual(
                    inspect.signature(getattr(sp2150, name)),
                    inspect.signature(getattr(virtual_sp2150, name)),
                )

    def test_disconnected_operations_match(self):
        for driver in (sp2150, virtual_sp2150):
            device = driver()
            for name in ("scan_speed", "wavelength", "grating", "turret", "filter", "grating_info", "turret_info"):
                with self.subTest(driver=driver, getter=name), self.assertRaisesRegex(RuntimeError, "not connected"):
                    getattr(device, name)
            for name in ("scan_speed", "wavelength", "grating", "turret", "filter"):
                with self.subTest(driver=driver, setter=name), self.assertRaisesRegex(RuntimeError, "not connected"):
                    setattr(device, name, 1)
            with self.assertRaisesRegex(RuntimeError, "not connected"):
                device.scan_to_wavelength(500)
            with self.assertRaisesRegex(RuntimeError, "not connected"):
                device.home_filter()
