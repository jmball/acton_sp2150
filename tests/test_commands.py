"""Check exact wire commands independently of the shared behavioral contract."""

import unittest
from unittest.mock import Mock

from sp2150 import sp2150
from tests.fakes import FakeSerial


class CommandTests(unittest.TestCase):
    def setUp(self):
        self.resource = FakeSerial()
        manager = Mock()
        manager.open_resource.return_value = self.resource
        self.device = sp2150()
        self.device.connect("ASRL2::INSTR", resource_manager=manager)
        self.resource.commands.clear()
        self.addCleanup(self.device.disconnect)

    def test_property_getter_commands(self):
        for name, command in {
            "scan_speed": "?NM/MIN", "wavelength": "?NM", "grating": "?GRATING",
            "turret": "?TURRET", "filter": "?FILTER",
        }.items():
            with self.subTest(name=name):
                getattr(self.device, name)
                self.assertEqual(self.resource.commands.pop(), command)

    def test_property_setter_commands(self):
        for name, value, command in (
            ("scan_speed", "123.46", "123.5 NM/MIN"),
            ("wavelength", "532.26", "532.3 GOTO"),
            ("grating", "2", "2 GRATING"),
            ("turret", "1", "1 TURRET"),
            ("filter", "3", "3 FILTER"),
        ):
            with self.subTest(name=name):
                setattr(self.device, name, value)
                self.assertEqual(self.resource.commands.pop(), command)

    def test_scan_command_and_readback(self):
        self.device.scan_to_wavelength("532.26")
        self.assertEqual(self.resource.commands, ["?NM", "?NM/MIN", "532.3 NM"])
        self.assertEqual(self.device.wavelength, 532.3)

    def test_home_command(self):
        self.device.home_filter()
        self.assertEqual(self.resource.commands, ["FHOME"])

    def test_query_preserves_response_while_property_parses_value(self):
        self.assertEqual(self.device._query("?NM/MIN"), " 1000.0 nm/min")
        self.assertEqual(self.device.scan_speed, 1000.0)

    def test_disconnected_communication_does_not_reach_resource(self):
        self.device.disconnect()
        for method, argument in (("_write", "?TURRETS"), ("_query", "FHOME"),
                                 ("_read_bytes", 1)):
            with self.subTest(method=method), self.assertRaisesRegex(RuntimeError, "not connected"):
                getattr(self.device, method)(argument)
        self.assertEqual(self.resource.commands, [])
        self.assertEqual(self.resource._pending, b"")

    def test_information_commands_preserve_internal_newlines_and_trailing_letters(self):
        for name, command in (("grating_info", "?GRATINGS"), ("turret_info", "?TURRETS")):
            with self.subTest(name=name):
                self.assertEqual(getattr(self.device, name), getattr(self.resource, name))
                self.assertEqual(self.resource.commands.pop(), command)
                self.assertEqual(self.resource._pending, b"")

    def test_incomplete_information_response_propagates_timeout(self):
        original_write = self.resource.write

        def incomplete_write(command):
            original_write(command)
            self.resource._pending = b" partial response\r\n"

        self.resource.write = incomplete_write
        with self.assertRaises(TimeoutError):
            _ = self.device.turret_info
