"""Pytest hardware options, fixtures, state restoration, and homing measurements."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import math
from time import perf_counter
from typing import Any

import pytest
import pyvisa

from sp2150 import sp2150
from sp2150.sp2150 import _discard_fixed_options
from tests.contract import ContractTargets


@dataclass
class HardwareOptions(ContractTargets):
    grating: int = 1
    resource_name: str = ""
    visa_backend: str = ""
    timeout: int = 30000
    home_repetitions: int = 1
    filter_home_timeout_ms: int | None = None
    resource_options: dict[str, Any] = field(default_factory=dict)


@dataclass
class HomingMeasurement:
    position: int
    repeat: int
    elapsed_ms: float
    allowance_ms: float

    def describe(self) -> str:
        margin = self.allowance_ms - self.elapsed_ms
        return (
            f"Homing from filter {self.position}, repeat {self.repeat}: "
            f"{self.elapsed_ms / 1000:.3f} s; allowance {self.allowance_ms / 1000:.3f} s; "
            f"headroom {margin / 1000:+.3f} s ({100 * margin / self.allowance_ms:+.1f}%)"
        )


_OPTIONS = pytest.StashKey[HardwareOptions]()
_MEASUREMENTS = pytest.StashKey[list[HomingMeasurement]]()


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("SP-2150 hardware")
    defaults = HardwareOptions()
    group.addoption(
        "--resource-name", help="VISA resource name or alias; enables hardware tests"
    )
    group.addoption("--visa-backend", default="", help="VISA backend, e.g. @py")
    group.addoption(
        "--timeout", type=int, default=30000, help="General hardware I/O timeout in ms"
    )
    group.addoption(
        "--wavelength",
        type=float,
        default=defaults.wavelength,
        help="Direct positioning target in nm",
    )
    group.addoption(
        "--scan-wavelength",
        type=float,
        default=defaults.scan_wavelength,
        help="Distinct scan target in nm",
    )
    group.addoption(
        "--scan-speed",
        type=float,
        default=defaults.scan_speed,
        help="Scan speed in nm/min",
    )
    group.addoption(
        "--grating",
        type=int,
        default=defaults.grating,
        help="Grating number to test (default: 1)",
    )
    group.addoption(
        "--turret",
        type=int,
        default=defaults.turret,
        help="Turret parameter set to test (default: 1)",
    )
    group.addoption(
        "--filter-position",
        type=int,
        default=defaults.filter_position,
        help="Filter wheel position to test",
    )
    group.addoption(
        "--home-filter-position",
        type=int,
        default=1,
        help="Expected position after FHOME",
    )
    group.addoption(
        "--home-repetitions",
        type=int,
        default=1,
        help="Timing-test sweeps of all six positions",
    )
    group.addoption(
        "--filter-home-timeout-ms",
        type=int,
        help="Homing allowance tested exactly (default: driver allowance)",
    )
    group.addoption(
        "--resource-option",
        action="append",
        default=[],
        metavar="KEY=JSON",
        help="Additional VISA resource option, repeatable",
    )


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers", "hardware: connects to real hardware only with --resource-name"
    )
    config.stash[_MEASUREMENTS] = []
    if config.getoption("resource_name") is None:
        return
    if not config.getoption("resource_name").strip():
        raise pytest.UsageError("--resource-name must not be empty")
    if config.getoption("numprocesses", default=0):
        raise pytest.UsageError(
            "Hardware tests must run sequentially; remove the -n option"
        )
    target_names = (
        "resource_name",
        "wavelength",
        "scan_wavelength",
        "grating",
        "turret",
        "filter_position",
    )
    for name in (
        "timeout",
        "grating",
        "turret",
        "filter_position",
        "home_filter_position",
        "home_repetitions",
        "filter_home_timeout_ms",
    ):
        value = config.getoption(name)
        if value is not None and value <= 0:
            raise pytest.UsageError(f"--{name.replace('_', '-')} must be positive")
    for name in ("wavelength", "scan_wavelength", "scan_speed"):
        value = config.getoption(name)
        if not math.isfinite(value) or value < 0:
            raise pytest.UsageError(
                f"--{name.replace('_', '-')} must be finite and nonnegative"
            )
    if round(config.getoption("scan_speed"), 1) <= 0:
        raise pytest.UsageError("--scan-speed must remain positive after rounding")
    if round(config.getoption("wavelength"), 1) == round(
        config.getoption("scan_wavelength"), 1
    ):
        raise pytest.UsageError("Wavelength targets must differ at 0.1 nm precision")
    options: dict[str, Any] = {}
    for item in config.getoption("resource_option"):
        key, separator, value = item.partition("=")
        if not separator or not key:
            raise pytest.UsageError("--resource-option must be KEY=JSON")
        if key in ("timeout", "resource_name", "resource_manager"):
            raise pytest.UsageError(
                f"Resource option {key!r} is controlled by the hardware runner"
            )
        if key in options:
            raise pytest.UsageError(f"Duplicate resource option: {key}")
        try:
            decoded = json.loads(value)
        except ValueError as exc:
            raise pytest.UsageError(
                f"Invalid JSON for resource option {key!r}"
            ) from exc
        if isinstance(decoded, (dict, list)):
            raise pytest.UsageError("Resource options must be JSON scalar values")
        options[key] = decoded
    _discard_fixed_options(options)
    config.stash[_OPTIONS] = HardwareOptions(
        **{name: config.getoption(name) for name in target_names},
        visa_backend=config.getoption("visa_backend"),
        timeout=config.getoption("timeout"),
        scan_speed=config.getoption("scan_speed"),
        home_filter_position=config.getoption("home_filter_position"),
        home_repetitions=config.getoption("home_repetitions"),
        filter_home_timeout_ms=config.getoption("filter_home_timeout_ms"),
        resource_options=options,
    )


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    if config.getoption("resource_name") is None:
        skip = pytest.mark.skip(reason="Real hardware requires --resource-name")
        for item in items:
            if item.get_closest_marker("hardware"):
                item.add_marker(skip)


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    if "home_start_position" in metafunc.fixturenames:
        repetitions = metafunc.config.getoption("home_repetitions")
        if repetitions <= 0:
            raise pytest.UsageError("--home-repetitions must be positive")
        metafunc.parametrize(
            "home_start_position,home_repeat",
            [
                pytest.param(
                    position, repeat, id=f"position-{position}-repeat-{repeat}"
                )
                for repeat in range(1, repetitions + 1)
                for position in range(1, 7)
            ],
        )


def pytest_terminal_summary(terminalreporter: Any) -> None:
    measurements = terminalreporter.config.stash.get(_MEASUREMENTS, [])
    if not measurements:
        return
    terminalreporter.write_sep("-", "Filter homing timings")
    for measurement in measurements:
        terminalreporter.write_line(measurement.describe())
    slowest = max(measurements, key=lambda measurement: measurement.elapsed_ms)
    terminalreporter.write_line(
        f"Slowest homing: filter {slowest.position}, repeat {slowest.repeat}, "
        f"{slowest.elapsed_ms / 1000:.3f} s; "
        f"headroom {(slowest.allowance_ms - slowest.elapsed_ms) / 1000:+.3f} s"
    )


@pytest.fixture
def hardware_options(pytestconfig: pytest.Config) -> HardwareOptions:
    if pytestconfig.getoption("resource_name") is None:
        pytest.skip("Hardware access is explicitly disabled")
    return pytestconfig.stash[_OPTIONS]


@pytest.fixture
def hardware_manager(hardware_options: HardwareOptions):
    manager = pyvisa.ResourceManager(hardware_options.visa_backend)
    try:
        yield manager
    finally:
        manager.close()


def restore_state(device: sp2150, initial_state: dict[str, Any]) -> None:
    """Attempt every state restoration during pytest teardown.

    Parameters
    ----------
    device : sp2150
        Connected hardware driver whose state is to be restored.
    initial_state : dict of str to object
        Previously recorded property values, restored in dictionary order.
        Attempt all properties even if an earlier restoration fails.
    """
    failures = []
    for name, value in initial_state.items():
        try:
            setattr(device, name, value)
        except Exception as exc:
            failures.append((name, exc))
    if failures:
        detail = "; ".join(f"{name}: {exc}" for name, exc in failures)
        raise RuntimeError(
            f"Could not restore initial instrument settings: {detail}"
        ) from failures[0][1]


@pytest.fixture
def hardware_device(
    request: pytest.FixtureRequest, hardware_options: HardwareOptions, hardware_manager
):
    device = sp2150()
    request.addfinalizer(device.disconnect)
    if hardware_options.filter_home_timeout_ms is not None:
        device.filter_home_timeout_ms = hardware_options.filter_home_timeout_ms
    device.connect(
        hardware_options.resource_name,
        resource_manager=hardware_manager,
        timeout=hardware_options.timeout,
        **hardware_options.resource_options,
    )
    initial_state = {
        name: getattr(device, name)
        for name in ("turret", "grating", "scan_speed", "wavelength", "filter")
    }
    request.addfinalizer(lambda: restore_state(device, initial_state))
    return device


def measure_homing(
    device: sp2150, position: int, repeat: int, config: pytest.Config
) -> HomingMeasurement:
    device.filter = position
    assert device.filter == position
    instr = device._instr
    assert instr is not None
    allowance = device.filter_home_timeout_ms
    old_timeout = instr.timeout
    instr.timeout = allowance
    start = perf_counter()
    try:
        device.home_filter()
    finally:
        measurement = HomingMeasurement(
            position, repeat, (perf_counter() - start) * 1000, allowance
        )
        config.stash[_MEASUREMENTS].append(measurement)
        instr.timeout = old_timeout
    return measurement
