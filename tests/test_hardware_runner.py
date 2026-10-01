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
            ["--resource-option", "timeout=1000"],
            ["--resource-option", "query_delay=broken"],
            ["--resource-option", "query_delay=0.1", "--resource-option", "query_delay=0.2"],
            ["--scan-speed", "0"], ["--scan-speed", "nan"],
            ["--scan-wavelength", "500"], ["--timeout", "-1"],
            ["--home-repetitions", "0"], ["--filter-home-timeout-ms", "0"],
        ):
            with self.subTest(extra=extra), redirect_stderr(io.StringIO()):
                factory = Mock()
                with self.assertRaises(SystemExit) as error:
                    hardware.main(self.arguments + extra, manager_factory=factory)
                self.assertEqual(error.exception.code, 2)
                factory.assert_not_called()

    def test_fixed_cli_options_warn_and_use_device_configuration(self):
        output = io.StringIO()
        with self.assertWarnsRegex(UserWarning, "baud_rate.*encoding"):
            result = hardware.main(
                self.arguments + ["--resource-option", "baud_rate=115200",
                                  "--resource-option", 'encoding="UTF-8"',
                                  "--test", "test_filter"],
                manager_factory=self.manager_factory, stream=output,
            )
        self.assertEqual(result, 0, output.getvalue())
        self.managers[0].open_resource.assert_called_once_with("ASRL2::INSTR", timeout=30000)
        self.assertEqual(self.resources[0].baud_rate, 9600)
        self.assertEqual(self.resources[0].encoding, "ASCII")
        self.assert_restored_and_closed()

    def test_hardware_targets_are_required_before_any_connection(self):
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            hardware.main(["--resource-name", "ASRL2::INSTR"], manager_factory=Mock())

    def test_homing_timing_covers_every_position_and_reports_worst_case(self):
        output = io.StringIO()
        durations = (1, 4, 8, 17.25, 10, 5)
        clock = [value for start, duration in zip(range(0, 120, 20), durations)
                 for value in (start, start + duration)]
        observed_timeouts = []

        def factory(backend):
            manager = self.manager_factory(backend)
            resource = self.resources[-1]
            original_query = resource.query

            def query(command):
                if command == "FHOME":
                    observed_timeouts.append(resource.timeout)
                return original_query(command)

            resource.query = query
            return manager

        with patch("tests.hardware.perf_counter", side_effect=clock):
            result = hardware.main(
                self.arguments + ["--test", "test_home_filter_timing"],
                manager_factory=factory, stream=output,
            )
        self.assertEqual(result, 0, output.getvalue())
        self.assertEqual(observed_timeouts, [20000] * 6)
        for position in range(1, 7):
            self.assertIn(f"Homing from filter {position}, repeat 1:", output.getvalue())
        self.assertIn("headroom +2.750 s (+13.8%)", output.getvalue())
        self.assertIn("Slowest homing: filter 4, repeat 1, 17.250 s", output.getvalue())
        self.assertEqual(self.resources[0].timeout, 30000)
        self.assert_restored_and_closed()

    def test_homing_timing_supports_repeats_and_custom_allowance(self):
        output = io.StringIO()
        observed_timeouts = []

        def factory(backend):
            manager = self.manager_factory(backend)
            resource = self.resources[-1]
            original_query = resource.query

            def query(command):
                if command == "FHOME":
                    observed_timeouts.append(resource.timeout)
                return original_query(command)

            resource.query = query
            return manager

        clock = [value for start in range(0, 24, 2) for value in (start, start + 1)]
        with patch("tests.hardware.perf_counter", side_effect=clock):
            result = hardware.main(
                self.arguments + ["--test", "test_home_filter_timing", "--home-repetitions", "2",
                                  "--filter-home-timeout-ms", "45000"],
                manager_factory=factory, stream=output,
            )
        self.assertEqual(result, 0, output.getvalue())
        self.assertEqual(observed_timeouts, [45000] * 12)
        self.assertIn("Homing from filter 6, repeat 2", output.getvalue())
        self.assertEqual(self.resources[0].timeout, 30000)
        self.assert_restored_and_closed()

    def test_homing_timing_fails_when_estimate_is_exceeded(self):
        output = io.StringIO()
        clock = [value for start in range(0, 180, 30) for value in (start, start + 21)]
        with patch("tests.hardware.perf_counter", side_effect=clock):
            result = hardware.main(
                self.arguments + ["--test", "test_home_filter_timing"],
                manager_factory=self.manager_factory, stream=output,
            )
        self.assertEqual(result, 1)
        self.assertIn("Homing exceeded its timeout allowance", output.getvalue())
        self.assertIn("headroom -1.000 s", output.getvalue())
        self.assertEqual(self.resources[0].timeout, 30000)
        self.assert_restored_and_closed()

    def test_homing_timeout_is_reported_with_timing_and_cleanup(self):
        output = io.StringIO()

        def factory(backend):
            manager = self.manager_factory(backend)
            self.resources[-1].fail_command = "FHOME"
            return manager

        clock = [value for start in range(0, 120, 20) for value in (start, start + 20)]
        with patch("tests.hardware.perf_counter", side_effect=clock):
            result = hardware.main(
                self.arguments + ["--test", "test_home_filter_timing"],
                manager_factory=factory, stream=output,
            )
        self.assertEqual(result, 1)
        self.assertIn("query failed", output.getvalue())
        self.assertIn("Homing from filter 6, repeat 1: 20.000 s", output.getvalue())
        self.assertEqual(self.resources[0].timeout, 30000)
        self.assert_restored_and_closed()

    def test_homing_timing_checks_final_position(self):
        output = io.StringIO()

        def factory(backend):
            manager = self.manager_factory(backend)
            resource = self.resources[-1]
            original_query = resource.query

            def query(command):
                result = original_query(command)
                if command == "FHOME":
                    resource.filter = 2
                return result

            resource.query = query
            return manager

        result = hardware.main(
            self.arguments + ["--test", "test_home_filter_timing"],
            manager_factory=factory, stream=output,
        )
        self.assertEqual(result, 1)
        self.assertIn("2 != 1", output.getvalue())
        self.assertEqual(self.resources[0].timeout, 30000)
        self.assert_restored_and_closed()
