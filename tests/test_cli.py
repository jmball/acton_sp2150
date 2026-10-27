"""Example argument handling and dispatch without hardware."""

from unittest.mock import patch

import pytest
from examples import cli

from tests.fakes import FakeSerial, make_manager


@pytest.mark.parametrize(
    "command,extra,expected",
    [
        ("get_scan_speed", [], "1000.0\n"),
        ("get_wavelength", [], "0.0\n"),
        ("get_grating", [], "1\n"),
        ("get_turret", [], "1\n"),
        ("get_filter", [], "1\n"),
        ("get_grating_info", [], "dummy info\n"),
        ("get_turret_info", [], "dummy info\n"),
        ("set_scan_speed", ["-p", "123.4"], ""),
        ("goto_wavelength", ["-p", "532.26"], ""),
        ("scan_to_wavelength", ["-p", "532.26"], ""),
        ("set_grating", ["-p", "2"], ""),
        ("set_turret", ["-p", "1"], ""),
        ("set_filter", ["-p", "3"], ""),
        ("home_filter", [], ""),
    ],
)
def test_simulator_command_never_constructs_manager(command, extra, expected, capsys):
    with patch("examples.cli.pyvisa.ResourceManager") as factory:
        assert cli.main(["--virtual", command, *extra]) == 0
        assert capsys.readouterr().out == expected
        factory.assert_not_called()


@pytest.fixture
def run_hardware_command():
    def run(command, *extra, fail_command=None):
        resource = FakeSerial()
        resource.fail_command = fail_command
        manager = make_manager(resource)
        with patch(
            "examples.cli.pyvisa.ResourceManager", return_value=manager
        ) as factory:
            try:
                cli.main(
                    [
                        "-n",
                        "ASRL2::INSTR",
                        "--visa-backend",
                        "@py",
                        "-t",
                        "45000",
                        command,
                        *extra,
                    ]
                )
            finally:
                factory.assert_called_once_with("@py")
                manager.open_resource.assert_called_once_with(
                    "ASRL2::INSTR", timeout=45000
                )
                assert resource.close_count == 1
                manager.close.assert_called_once()
        return resource

    return run


@pytest.mark.parametrize(
    "command,parameter,expected",
    [
        ("set_scan_speed", "123.46", "123.5 NM/MIN"),
        ("goto_wavelength", "532.26", "532.3 GOTO"),
        ("scan_to_wavelength", "532.26", "532.3 NM"),
        ("set_grating", "2", "2 GRATING"),
        ("set_turret", "1", "1 TURRET"),
        ("set_filter", "3", "3 FILTER"),
    ],
)
def test_hardware_dispatch_and_cleanup(
    run_hardware_command, command, parameter, expected
):
    resource = run_hardware_command(command, "-p", parameter)
    assert resource.commands[-1] == expected


@pytest.mark.parametrize("command", ["NO-ECHO", "FHOME"])
def test_failure_closes_instrument_and_cli_owned_manager(run_hardware_command, command):
    with pytest.raises(TimeoutError):
        run_hardware_command("home_filter", fail_command=command)


@pytest.mark.parametrize(
    "argv",
    [
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
    ],
)
def test_invalid_arguments_never_connect(argv, capsys):
    with (
        patch("examples.cli.sp2150") as driver,
        patch("examples.cli.virtual_sp2150") as simulator,
        patch("examples.cli.pyvisa.ResourceManager") as manager,
    ):
        with pytest.raises(SystemExit) as error:
            cli.main(argv)
        assert error.value.code == 2
        assert capsys.readouterr().err
        driver.assert_not_called()
        simulator.assert_not_called()
        manager.assert_not_called()


def test_help_never_connects(capsys):
    with (
        patch("examples.cli.pyvisa.ResourceManager") as manager,
        pytest.raises(SystemExit) as error,
    ):
        cli.main(["--help"])
    assert error.value.code == 0
    assert "--virtual" in capsys.readouterr().out
    manager.assert_not_called()
