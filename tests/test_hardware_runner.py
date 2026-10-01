"""Validate the opt-in hardware harness itself, using only fake resources."""

from contextlib import redirect_stderr
import io
import unittest
from unittest.mock import Mock, patch

from tests import hardware
from tests.fakes import FakeSerial, make_manager


class HardwareRunnerTests(unittest.TestCase):
    def setUp(self):
        self.arguments = [
            "--resource-name", "ASRL2::INSTR", "--visa-backend", "@py",
            "--wavelength", "500", "--scan-wavelength", "501",
            "--grating", "2", "--turret", "1", "--filter-position", "3",
        ]
        self.resources = []
        self.managers = []

    def manager_factory(self, backend):
        self.assertEqual(backend, "@py")
        resource = FakeSerial()
        manager = make_manager(resource)
        self.resources.append(resource)
        self.managers.append(manager)
        return manager

    def assert_restored_and_closed(self):
        for resource in self.resources:
            self.assertEqual(resource.wavelength, 0.0)
            self.assertEqual(resource.scan_speed, 1000.0)
            self.assertEqual(resource.grating, 1)
            self.assertEqual(resource.turret, 1)
            self.assertEqual(resource.filter, 1)
            self.assertEqual(resource.close_count, 1)
        for manager in self.managers:
            manager.close.assert_called_once()

    def test_full_hardware_suite_exercises_every_command_and_restores_state(self):
        output = io.StringIO()
        result = hardware.main(self.arguments, manager_factory=self.manager_factory, stream=output)
        self.assertEqual(result, 0, output.getvalue())
        commands = {command for resource in self.resources for command in resource.commands}
        self.assertTrue({
            "NO-ECHO", "?NM/MIN", "?NM", "?GRATING", "?TURRET", "?FILTER",
            "?GRATINGS", "?TURRETS", "600.0 NM/MIN", "500.0 GOTO", "501.0 NM",
            "2 GRATING", "1 TURRET", "3 FILTER", "FHOME",
        }.issubset(commands), commands)
        self.assert_restored_and_closed()

    def test_restoration_and_disconnect_run_after_a_command_failure(self):
        def factory(backend):
            manager = self.manager_factory(backend)
            self.resources[-1].fail_command = "501.0 NM"
            return manager

        output = io.StringIO()
        result = hardware.main(
            self.arguments + ["--test", "test_scanned_wavelength"],
            manager_factory=factory, stream=output,
        )
        self.assertEqual(result, 1)
        self.assertIn("query failed", output.getvalue())
        self.assert_restored_and_closed()

    def test_turret_info_failure_is_reported_as_an_error_not_skipped(self):
        def factory(backend):
            manager = self.manager_factory(backend)
            self.resources[-1].fail_command = "?TURRETS"
            return manager

        output = io.StringIO()
        result = hardware.main(
            self.arguments + ["--test", "test_turret_information"],
            manager_factory=factory, stream=output,
        )
        self.assertEqual(result, 1)
        self.assertIn("ERROR", output.getvalue())
        self.assert_restored_and_closed()

    def test_cleanup_attempts_remaining_settings_when_one_restore_fails(self):
        output = io.StringIO()
        with patch("tests.hardware.HardwareTests.test_direct_wavelength", create=True) as command:
            def fail_restoration():
                self.resources[-1].fail_command = "1 TURRET"

            command.side_effect = fail_restoration
            result = hardware.main(
                self.arguments + ["--test", "test_direct_wavelength"],
                manager_factory=self.manager_factory, stream=output,
            )
        self.assertEqual(result, 1)
        self.assertIn("Could not restore", output.getvalue())
        self.assertIn("0.0 GOTO", self.resources[0].commands)
        self.assertEqual(self.resources[0].close_count, 1)
        self.managers[0].close.assert_called_once()

    def test_initial_connection_failure_still_closes_manager(self):
        def factory(backend):
            manager = self.manager_factory(backend)
            manager.open_resource.side_effect = OSError("unreachable")
            return manager

        output = io.StringIO()
        result = hardware.main(
            self.arguments + ["--test", "test_direct_wavelength"],
            manager_factory=factory, stream=output,
        )
        self.assertEqual(result, 1)
        self.assertIn("unreachable", output.getvalue())
        self.managers[0].close.assert_called_once()

    def test_connection_options_are_passed_to_driver(self):
        output = io.StringIO()
        result = hardware.main(
            self.arguments + ["--timeout", "45000", "--resource-option", "query_delay=0.05",
                              "--resource-option", "open_timeout=2000", "--test", "test_filter"],
            manager_factory=self.manager_factory, stream=output,
        )
        self.assertEqual(result, 0, output.getvalue())
        self.assertEqual(self.resources[0].timeout, 45000)
        self.assertEqual(self.resources[0].query_delay, 0.05)
        self.managers[0].open_resource.assert_called_once_with(
            "ASRL2::INSTR", open_timeout=2000, timeout=45000, query_delay=0.05
        )

    def test_invalid_cli_options_never_create_a_manager(self):
        for extra in (
            ["--resource-option", "baud_rate=9600"],
            ["--resource-option", "timeout=1000"],
            ["--resource-option", "query_delay=broken"],
            ["--resource-option", "query_delay=0.1", "--resource-option", "query_delay=0.2"],
            ["--scan-speed", "0"], ["--scan-speed", "nan"],
            ["--scan-wavelength", "500"], ["--timeout", "-1"],
        ):
            with self.subTest(extra=extra), redirect_stderr(io.StringIO()):
                factory = Mock()
                with self.assertRaises(SystemExit) as error:
                    hardware.main(self.arguments + extra, manager_factory=factory)
                self.assertEqual(error.exception.code, 2)
                factory.assert_not_called()

    def test_hardware_targets_are_required_before_any_connection(self):
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            hardware.main(["--resource-name", "ASRL2::INSTR"], manager_factory=Mock())
