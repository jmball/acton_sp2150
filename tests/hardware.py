"""Explicit hardware runner: uv run python -m tests.hardware --help.

This module is deliberately outside unittest's test*.py discovery pattern.
Importing it never constructs a manager or contacts an instrument.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import json
import math
import sys
from time import perf_counter
from typing import Any, Callable, Sequence, TextIO
import unittest

import pyvisa

from sp2150 import sp2150
from sp2150.sp2150 import _discard_fixed_options
from tests.contract import InstrumentContract


@dataclass
class HardwareOptions:
    resource_name: str
    wavelength: float
    scan_wavelength: float
    grating: int
    turret: int
    filter_position: int
    visa_backend: str = ""
    timeout: int = 30000
    scan_speed: float = 600.0
    home_filter_position: int = 1
    home_repetitions: int = 1
    filter_home_timeout_ms: int | None = None
    resource_options: dict[str, Any] = field(default_factory=dict)


class HardwareTests(InstrumentContract, unittest.TestCase):
    """Run each command test with a connection and independent state restoration."""

    def __init__(
        self,
        method_name: str,
        options: HardwareOptions,
        manager_factory: Callable[[str], pyvisa.ResourceManager] | None = None,
        *,
        timing_stream: TextIO | None = None,
    ) -> None:
        super().__init__(method_name)
        self.options = options
        self.manager_factory = manager_factory
        self.timing_stream = timing_stream if timing_stream is not None else sys.stderr
        self.wavelength_target = options.wavelength
        self.scan_target = options.scan_wavelength
        self.scan_speed_target = options.scan_speed
        self.grating_target = options.grating
        self.turret_target = options.turret
        self.filter_target = options.filter_position
        self.home_filter_position = options.home_filter_position

    def setUp(self) -> None:
        factory = self.manager_factory or pyvisa.ResourceManager
        manager = factory(self.options.visa_backend)
        # unittest runs cleanups in reverse order, even when a test fails.
        self.addCleanup(manager.close)
        self.device = sp2150()
        if self.options.filter_home_timeout_ms is not None:
            self.device.filter_home_timeout_ms = self.options.filter_home_timeout_ms
        self.addCleanup(self.device.disconnect)
        self.device.connect(
            self.options.resource_name,
            resource_manager=manager,
            timeout=self.options.timeout,
            **self.options.resource_options,
        )
        self.initial_state = {
            name: getattr(self.device, name)
            for name in ("turret", "grating", "scan_speed", "wavelength", "filter")
        }
        self.addCleanup(self.restore_state)

    def test_home_filter_timing(self) -> None:
        """Measure homing from every position, testing the exact homing allowance."""
        instr = self.device._instr
        assert instr is not None
        allowance_ms = self.device.filter_home_timeout_ms
        measurements: list[tuple[int, int, float]] = []
        for repeat in range(1, self.options.home_repetitions + 1):
            for position in range(1, 7):
                with self.subTest(position=position, repeat=repeat):
                    self.device.filter = position
                    self.assertEqual(self.device.filter, position)
                    old_timeout = instr.timeout
                    # A longer general I/O timeout must not hide a bad estimate.
                    instr.timeout = allowance_ms
                    start = perf_counter()
                    try:
                        self.device.home_filter()
                    finally:
                        elapsed_ms = (perf_counter() - start) * 1000
                        measurements.append((position, repeat, elapsed_ms))
                        margin_ms = allowance_ms - elapsed_ms
                        print(
                            f"\nHoming from filter {position}, repeat {repeat}: "
                            f"{elapsed_ms / 1000:.3f} s; allowance {allowance_ms / 1000:.3f} s; "
                            f"headroom {margin_ms / 1000:+.3f} s "
                            f"({100 * margin_ms / allowance_ms:+.1f}%)",
                            file=self.timing_stream, flush=True,
                        )
                        instr.timeout = old_timeout
                    self.assertEqual(self.device.filter, self.home_filter_position)
                    self.assertLessEqual(elapsed_ms, allowance_ms, "Homing exceeded its timeout allowance")
        if measurements:
            position, repeat, elapsed_ms = max(measurements, key=lambda measurement: measurement[2])
            print(
                f"\nSlowest homing: filter {position}, repeat {repeat}, {elapsed_ms / 1000:.3f} s; "
                f"headroom {(allowance_ms - elapsed_ms) / 1000:+.3f} s",
                file=self.timing_stream, flush=True,
            )

    def restore_state(self) -> None:
        """Attempt every restoration, then report any failure to unittest."""
        failures = []
        for name, value in self.initial_state.items():
            try:
                setattr(self.device, name, value)
            except Exception as exc:
                failures.append((name, exc))
        if failures:
            detail = "; ".join(f"{name}: {exc}" for name, exc in failures)
            raise RuntimeError(f"Could not restore initial instrument settings: {detail}") from failures[0][1]


def build_suite(
    options: HardwareOptions,
    names: Sequence[str] | None = None,
    manager_factory: Callable[[str], pyvisa.ResourceManager] | None = None,
    *,
    timing_stream: TextIO | None = None,
) -> unittest.TestSuite:
    names = names or unittest.defaultTestLoader.getTestCaseNames(HardwareTests)
    return unittest.TestSuite(
        HardwareTests(name, options, manager_factory, timing_stream=timing_stream)
        for name in names
    )


def _positive_int(value: str) -> int:
    result = int(value)
    if result <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return result


def _nonnegative_float(value: str) -> float:
    result = float(value)
    if not math.isfinite(result) or result < 0:
        raise argparse.ArgumentTypeError("must be a finite, nonnegative number")
    return result


def parse_options(argv: Sequence[str] | None = None) -> tuple[HardwareOptions, list[str] | None]:
    parser = argparse.ArgumentParser(
        description=(
            "Exercise all SP-2150 commands on connected hardware. Tests move the "
            "instrument and attempt to restore initial settings after each test."
        )
    )
    parser.add_argument("-n", "--resource-name", required=True, help="VISA name or alias")
    parser.add_argument("--visa-backend", default="", help="VISA library/backend, e.g. @py")
    parser.add_argument("-t", "--timeout", type=_positive_int, default=30000, help="I/O timeout in ms")
    parser.add_argument("--wavelength", type=_nonnegative_float, required=True, help="Direct positioning target in nm")
    parser.add_argument("--scan-wavelength", type=_nonnegative_float, required=True, help="Distinct scan target in nm")
    parser.add_argument("--scan-speed", type=_nonnegative_float, default=600.0, help="Scan speed in nm/min")
    parser.add_argument("--grating", type=_positive_int, required=True, help="Installed grating number on the selected turret")
    parser.add_argument("--turret", type=_positive_int, required=True, help="Installed turret number")
    parser.add_argument("--filter-position", type=_positive_int, required=True, help="Valid filter wheel position")
    parser.add_argument("--home-filter-position", type=_positive_int, default=1, help="Expected position after FHOME (default: 1)")
    parser.add_argument("--home-repetitions", type=_positive_int, default=1, help="Timing-test sweeps of all six filter positions")
    parser.add_argument("--filter-home-timeout-ms", type=_positive_int, help="Homing allowance in ms (default: driver's allowance), tested exactly by the timing test")
    parser.add_argument(
        "--resource-option", action="append", default=[], metavar="KEY=JSON",
        help="Additional driver resource option, repeatable (e.g. query_delay=0.05)",
    )
    parser.add_argument(
        "--test", action="append", choices=unittest.defaultTestLoader.getTestCaseNames(HardwareTests),
        help="Run only this test; repeat to select multiple tests",
    )
    args = parser.parse_args(argv)
    if round(args.scan_speed, 1) <= 0:
        parser.error("--scan-speed must be at least 0.1 nm/min after rounding")
    if round(args.wavelength, 1) == round(args.scan_wavelength, 1):
        parser.error("wavelength targets must differ at the driver's 0.1 nm precision")
    resource_options: dict[str, Any] = {}
    for item in args.resource_option:
        key, separator, value = item.partition("=")
        if not separator or not key:
            parser.error("--resource-option must be KEY=JSON")
        if key == "timeout":
            parser.error("use --timeout instead of --resource-option timeout")
        if key in resource_options:
            parser.error(f"duplicate resource option: {key}")
        try:
            decoded = json.loads(value)
        except ValueError:
            parser.error(f"invalid JSON for resource option {key!r}")
        if isinstance(decoded, (dict, list)):
            parser.error("resource options must be JSON scalar values")
        resource_options[key] = decoded
    _discard_fixed_options(resource_options)
    options = HardwareOptions(
        resource_name=args.resource_name,
        visa_backend=args.visa_backend,
        timeout=args.timeout,
        wavelength=args.wavelength,
        scan_wavelength=args.scan_wavelength,
        scan_speed=args.scan_speed,
        grating=args.grating,
        turret=args.turret,
        filter_position=args.filter_position,
        home_filter_position=args.home_filter_position,
        home_repetitions=args.home_repetitions,
        filter_home_timeout_ms=args.filter_home_timeout_ms,
        resource_options=resource_options,
    )
    return options, args.test


def main(
    argv: Sequence[str] | None = None,
    *,
    manager_factory: Callable[[str], pyvisa.ResourceManager] | None = None,
    stream: TextIO | None = None,
) -> int:
    options, names = parse_options(argv)
    result = unittest.TextTestRunner(verbosity=2, stream=stream).run(
        build_suite(options, names, manager_factory, timing_stream=stream)
    )
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
