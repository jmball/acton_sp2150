"""Exercise example argument handling and dispatch without hardware."""

from contextlib import redirect_stderr, redirect_stdout
import io
import unittest
from unittest.mock import patch

from examples import cli
from tests.fakes import FakeSerial, make_manager


class CliTests(unittest.TestCase):
    def test_every_command_runs_against_simulator_without_a_manager(self):
        commands = {
            "get_scan_speed": ([], "1000.0\n"),
            "get_wavelength": ([], "0.0\n"),
            "get_grating": ([], "1\n"), "get_turret": ([], "1\n"),
            "get_filter": ([], "1\n"),
            "get_grating_info": ([], "dummy info\n"),
            "get_turret_info": ([], "dummy info\n"),
            "set_scan_speed": (["-p", "123.4"], ""),
            "goto_wavelength": (["-p", "532.26"], ""),
            "scan_to_wavelength": (["-p", "532.26"], ""),
            "set_grating": (["-p", "2"], ""),
            "set_turret": (["-p", "1"], ""),
            "set_filter": (["-p", "3"], ""), "home_filter": ([], ""),
        }
        with patch("examples.cli.pyvisa.ResourceManager") as factory:
            for command, (extra, expected) in commands.items():
                with self.subTest(command=command), redirect_stdout(io.StringIO()) as output:
                    self.assertEqual(cli.main(["--virtual", command, *extra]), 0)
                    self.assertEqual(output.getvalue(), expected)
            factory.assert_not_called()

    def run_hardware_command(self, command, *extra, fail_command=None):
        resource = FakeSerial()
        resource.fail_command = fail_command
        manager = make_manager(resource)
        with patch("examples.cli.pyvisa.ResourceManager", return_value=manager) as factory:
            try:
                with redirect_stdout(io.StringIO()):
                    cli.main(["-n", "ASRL2::INSTR", "--visa-backend", "@py",
                              "-t", "45000", command, *extra])
            finally:
                factory.assert_called_once_with("@py")
                manager.open_resource.assert_called_once_with("ASRL2::INSTR", timeout=45000)
                self.assertEqual(resource.close_count, 1)
                manager.close.assert_called_once()
        return resource

    def test_hardware_dispatch_and_cleanup(self):
        for command, parameter, expected in (
            ("set_scan_speed", "123.46", "123.5 NM/MIN"),
            ("goto_wavelength", "532.26", "532.3 GOTO"),
            ("scan_to_wavelength", "532.26", "532.3 NM"),
            ("set_grating", "2", "2 GRATING"),
            ("set_turret", "1", "1 TURRET"),
            ("set_filter", "3", "3 FILTER"),
        ):
            with self.subTest(command=command):
                resource = self.run_hardware_command(command, "-p", parameter)
                self.assertEqual(resource.commands[-1], expected)

    def test_failure_closes_instrument_and_cli_owned_manager(self):
        for command in ("NO-ECHO", "FHOME"):
            with self.subTest(command=command), self.assertRaises(TimeoutError):
                self.run_hardware_command("home_filter", fail_command=command)

    def test_invalid_arguments_never_connect(self):
        arguments = (
            ["get_wavelength"],
            ["--virtual", "goto_wavelength"],
            ["--virtual", "set_grating", "-p", "1.5"],
            ["--virtual", "goto_wavelength", "-p", "bad"],
            ["--virtual", "goto_wavelength", "-p", "nan"],
            ["--virtual", "scan_to_wavelength", "-p", "inf"],
            ["--virtual", "set_scan_speed", "-p", "0"],
            ["--virtual", "set_scan_speed", "-p", "0.01"],
            ["--virtual", "get_wavelength", "-p", "2"],
            ["--virtual", "home_filter", "-t", "-1"],
            ["--virtual", "home_filter", "--visa-backend", "@py"],
            ["--virtual", "unknown"],
        )
        with patch("examples.cli.sp2150") as driver, \
                patch("examples.cli.virtual_sp2150") as simulator, \
                patch("examples.cli.pyvisa.ResourceManager") as manager:
            for argv in arguments:
                with self.subTest(argv=argv), redirect_stderr(io.StringIO()):
                    with self.assertRaises(SystemExit) as error:
                        cli.main(argv)
                    self.assertEqual(error.exception.code, 2)
            driver.assert_not_called()
            simulator.assert_not_called()
            manager.assert_not_called()

    def test_help_never_connects(self):
        with patch("examples.cli.pyvisa.ResourceManager") as manager, \
                redirect_stdout(io.StringIO()) as output, self.assertRaises(SystemExit) as error:
            cli.main(["--help"])
        self.assertEqual(error.exception.code, 0)
        self.assertIn("--virtual", output.getvalue())
        manager.assert_not_called()
