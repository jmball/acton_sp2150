"""Exercise native pytest hardware collection and teardown using fake VISA only."""

import json
from pathlib import Path

import pytest


HARDWARE_ARGS = [
    "--run-hardware", "--resource-name", "ASRL2::INSTR", "--visa-backend=@py",
    "--wavelength", "500", "--scan-wavelength", "501", "--grating", "2",
    "--turret", "1", "--filter-position", "3",
]


@pytest.fixture
def hardware_project(pytester, monkeypatch):
    # Protect configuration/collection too, before the inner autouse fixture runs.
    from unittest.mock import Mock
    monkeypatch.setattr("pyvisa.ResourceManager", Mock(side_effect=AssertionError("Unexpected early hardware access")))
    source = Path(__file__).with_name("test_hardware.py").read_text()
    pytester.makepyfile(test_hardware=source)
    pytester.makeconftest('''
import json
from pathlib import Path
from unittest.mock import Mock
import pytest
import pyvisa
from tests.fakes import FakeSerial, make_manager
import tests.hardware as hardware
pytest_plugins = ["tests.hardware"]
clock = None

@pytest.fixture(autouse=True)
def fake_backend(monkeypatch):
    global clock
    settings_path = Path("settings.json")
    settings = json.loads(settings_path.read_text()) if settings_path.exists() else {}
    if "clock" in settings:
        if clock is None:
            clock = iter(settings["clock"])
        monkeypatch.setattr(hardware, "perf_counter", lambda: next(clock))

    def factory(backend):
        assert backend == "@py"
        Path("opened").touch()
        resource = FakeSerial()
        resource.fail_command = settings.get("fail_command")
        manager = make_manager(resource)
        if settings.get("open_failure"):
            manager.open_resource.side_effect = OSError("unreachable")
        original_query = resource.query
        def query(command):
            if command == settings.get("fail_restoration"):
                raise OSError("restoration failed")
            result = original_query(command)
            if command == "FHOME":
                if settings.get("wrong_home"):
                    resource.filter = 2
                with Path("home_timeouts.jsonl").open("a") as out:
                    out.write(json.dumps(resource.timeout) + "\\n")
            return result
        resource.query = query
        def close():
            record = dict(wavelength=resource.wavelength, scan_speed=resource.scan_speed,
                          grating=resource.grating, turret=resource.turret, filter=resource.filter,
                          timeout=resource.timeout, close_count=resource.close_count,
                          commands=resource.commands, open_options=manager.open_resource.call_args.kwargs)
            with Path("closed.jsonl").open("a") as out:
                out.write(json.dumps(record) + "\\n")
        manager.close.side_effect = close
        return manager
    monkeypatch.setattr(pyvisa, "ResourceManager", factory)
''')
    return pytester


def records(project, name="closed.jsonl"):
    path = project.path / name
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def assert_restored(project):
    entries = records(project)
    assert entries
    for record in entries:
        assert (record["wavelength"], record["scan_speed"], record["grating"], record["turret"], record["filter"]) == (0, 1000, 1, 1, 1)
        assert record["close_count"] == 1


def configure(project, **settings):
    (project.path / "settings.json").write_text(json.dumps(settings))


def test_default_collection_never_opens_hardware(hardware_project):
    result = hardware_project.runpytest("-q")
    result.assert_outcomes(skipped=15)
    assert not (hardware_project.path / "opened").exists()


def test_collect_only_never_opens_hardware(hardware_project):
    result = hardware_project.runpytest("--collect-only", "-q", *HARDWARE_ARGS)
    assert result.ret == 0
    assert not (hardware_project.path / "opened").exists()


def test_mark_selection_still_requires_explicit_hardware_flag(hardware_project):
    result = hardware_project.runpytest("-q", "-m", "hardware")
    result.assert_outcomes(skipped=15)
    assert not (hardware_project.path / "opened").exists()


def test_parallel_hardware_execution_is_rejected(hardware_project):
    conftest = hardware_project.path / "conftest.py"
    with conftest.open("a") as output:
        output.write('\ndef pytest_addoption(parser):\n    parser.addoption("--numprocesses", type=int, default=0)\n')
    result = hardware_project.runpytest("-q", *HARDWARE_ARGS, "--numprocesses", "2")
    assert result.ret == pytest.ExitCode.USAGE_ERROR
    assert "Hardware tests must run sequentially" in result.stderr.str()
    assert not (hardware_project.path / "opened").exists()


def test_full_hardware_suite_exercises_commands_and_restores(hardware_project):
    result = hardware_project.runpytest("-q", *HARDWARE_ARGS)
    result.assert_outcomes(passed=15)
    commands = {command for entry in records(hardware_project) for command in entry["commands"]}
    assert {"NO-ECHO", "?NM/MIN", "?NM", "?GRATING", "?TURRET", "?FILTER",
            "?GRATINGS", "?TURRETS", "600.0 NM/MIN", "500.0 GOTO", "501.0 NM",
            "2 GRATING", "1 TURRET", "3 FILTER", "FHOME"} <= commands
    assert_restored(hardware_project)


@pytest.mark.parametrize("name,command", [("test_scanned_wavelength", "501.0 NM"),
                                         ("test_turret_information", "?TURRETS")])
def test_command_failure_is_reported_and_restored(hardware_project, name, command):
    configure(hardware_project, fail_command=command)
    result = hardware_project.runpytest("-q", *HARDWARE_ARGS, "-k", name)
    result.assert_outcomes(failed=1, deselected=14)
    assert "query failed" in result.stdout.str()
    assert_restored(hardware_project)


def test_restoration_attempts_remaining_settings(hardware_project):
    configure(hardware_project, fail_restoration="1 TURRET")
    result = hardware_project.runpytest("-q", *HARDWARE_ARGS, "-k", "test_direct_wavelength")
    result.assert_outcomes(passed=1, errors=1, deselected=14)
    assert "Could not restore" in result.stdout.str()
    entry = records(hardware_project)[0]
    assert "0.0 GOTO" in entry["commands"]
    assert entry["close_count"] == 1


def test_initial_connection_failure_closes_manager(hardware_project):
    configure(hardware_project, open_failure=True)
    result = hardware_project.runpytest("-q", *HARDWARE_ARGS, "-k", "test_direct_wavelength")
    result.assert_outcomes(errors=1, deselected=14)
    assert "unreachable" in result.stdout.str()
    assert len(records(hardware_project)) == 1


def test_connection_options_are_forwarded(hardware_project):
    result = hardware_project.runpytest("-q", *HARDWARE_ARGS, "-k", "test_filter",
                                      "--timeout", "45000", "--resource-option", "query_delay=0.05",
                                      "--resource-option", "open_timeout=2000")
    result.assert_outcomes(passed=1, deselected=14)
    assert records(hardware_project)[0]["open_options"] == dict(timeout=45000, query_delay=0.05, open_timeout=2000)
    assert_restored(hardware_project)


@pytest.mark.parametrize("extra", [
    ["--resource-option", "timeout=1000"], ["--resource-option", "query_delay=broken"],
    ["--resource-option", "query_delay=0.1", "--resource-option", "query_delay=0.2"],
    ["--scan-speed", "0"], ["--scan-speed", "0.049"], ["--scan-speed", "nan"], ["--scan-wavelength", "500"],
    ["--wavelength", "0", "--scan-wavelength", "-0.0"],
    ["--timeout", "-1"], ["--home-repetitions", "0"], ["--filter-home-timeout-ms", "0"],
])
def test_invalid_options_never_open_hardware(hardware_project, extra):
    result = hardware_project.runpytest("-q", *HARDWARE_ARGS, *extra)
    assert result.ret == pytest.ExitCode.USAGE_ERROR
    assert not (hardware_project.path / "opened").exists()


def test_targets_are_required_before_connection(hardware_project):
    result = hardware_project.runpytest("-q", "--run-hardware", "--resource-name", "ASRL2::INSTR")
    assert result.ret == pytest.ExitCode.USAGE_ERROR
    assert not (hardware_project.path / "opened").exists()


def test_fixed_resource_options_warn_and_are_ignored(hardware_project):
    with pytest.warns(UserWarning, match="Ignoring driver-managed resource options: baud_rate, encoding"):
        result = hardware_project.runpytest("-q", *HARDWARE_ARGS, "-k", "test_filter",
                                          "--resource-option", "baud_rate=115200",
                                          "--resource-option", 'encoding="UTF-8"')
    result.assert_outcomes(passed=1, deselected=14)
    assert records(hardware_project)[0]["open_options"] == dict(timeout=30000)


def test_homing_reports_every_position_and_worst_case(hardware_project):
    durations = [1, 4, 8, 17.25, 10, 5]
    clock = [value for start, duration in zip(range(0, 120, 20), durations) for value in (start, start + duration)]
    configure(hardware_project, clock=clock)
    result = hardware_project.runpytest("-q", *HARDWARE_ARGS, "-k", "test_home_filter_timing")
    result.assert_outcomes(passed=6, deselected=9)
    for position in range(1, 7):
        assert f"Homing from filter {position}, repeat 1:" in result.stdout.str()
    assert "headroom +2.750 s (+13.8%)" in result.stdout.str()
    assert "Slowest homing: filter 4, repeat 1, 17.250 s" in result.stdout.str()
    assert records(hardware_project, "home_timeouts.jsonl") == [20000] * 6
    assert all(entry["timeout"] == 30000 for entry in records(hardware_project))
    assert_restored(hardware_project)


def test_homing_supports_repeats_and_custom_allowance(hardware_project):
    clock = [value for start in range(0, 24, 2) for value in (start, start + 1)]
    configure(hardware_project, clock=clock)
    result = hardware_project.runpytest("-q", *HARDWARE_ARGS, "-k", "test_home_filter_timing",
                                      "--home-repetitions", "2", "--filter-home-timeout-ms", "45000")
    result.assert_outcomes(passed=12, deselected=9)
    assert "Homing from filter 6, repeat 2" in result.stdout.str()
    assert records(hardware_project, "home_timeouts.jsonl") == [45000] * 12
    assert all(entry["timeout"] == 30000 for entry in records(hardware_project))
    assert_restored(hardware_project)


@pytest.mark.parametrize("failure", ["exceeded", "timeout", "wrong_position"])
def test_homing_failures_report_measurements_and_cleanup(hardware_project, failure):
    durations = 21 if failure == "exceeded" else 20
    clock = [value for start in range(0, 180, 30) for value in (start, start + durations)]
    configure(hardware_project, clock=clock, fail_command="FHOME" if failure == "timeout" else None,
              wrong_home=failure == "wrong_position")
    result = hardware_project.runpytest("-q", *HARDWARE_ARGS, "-k", "test_home_filter_timing")
    result.assert_outcomes(failed=6, deselected=9)
    message = {"exceeded": "Homing exceeded its timeout allowance", "timeout": "query failed",
               "wrong_position": "2 == 1"}[failure]
    assert message in result.stdout.str()
    assert "Homing from filter 6, repeat 1:" in result.stdout.str()
    assert all(entry["timeout"] == 30000 for entry in records(hardware_project))
    assert_restored(hardware_project)
