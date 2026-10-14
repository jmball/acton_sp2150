# Repository guide

## Purpose and layout

This repository controls a Princeton Instruments Acton SP-2150 monochromator
and FA-2448 filter wheel.

- `src/sp2150/sp2150.py`: PyVISA hardware driver.
- `src/virtual_sp2150/virtual_sp2150.py`: in-memory simulator with the same public
  API; it does not emulate VISA communication.
- `examples/cli.py`: argparse command-line example for hardware and simulation
  (`--virtual`). Validate arguments before creating a resource manager or driver.
- Both packages export a lowercase `sp2150` class through `__init__.py` and
  obtain `__version__` using `importlib.metadata` and the distribution name
  `acton_sp2150`, falling back to `0.0.0` when it is not installed.
- `pyproject.toml`: setuptools build configuration, package metadata, version,
  dependency declarations, and `src` package discovery.
  The distribution name is `acton_sp2150`; import names are
  `sp2150` and `virtual_sp2150`.
- `uv.lock`: committed dependency resolution for reproducible development.
- `MANIFEST.in`: includes tests, examples, and uv.lock in source archives. Installation
  metadata and build configuration remain in `pyproject.toml`.
- `LICENSE`: MIT license; keep package metadata consistent with this file.

## Development and validation

Default to uv for this repository. From the repository root, create or sync the
project environment and install the package in editable mode:

```sh
uv sync --locked
```

Runtime dependencies are `pyvisa` and `pyvisa-py`. Hardware access also needs a
working VISA backend and the dependencies appropriate to the connection type.
The package requires Python >=3.10. Preserve that minimum when changing syntax
or dependencies. Use `uv run` for project commands, `uv add`/`uv remove` for
dependency changes, and `uv lock` after editing dependency declarations by hand.
Commit `uv.lock` updates alongside the corresponding `pyproject.toml` changes.
Use setuptools as the build backend; do not introduce Hatchling.

Tests use native pytest functions, fixtures, and parametrisation. Pytest is a
locked development dependency. Keep test configuration in pyproject.toml:

- `tests/test_virtual.py`: simulator state, lifecycle, and simulated experiments.
- `tests/contract.py` and `tests/test_contract.py`: shared command behavior for the
  simulator and fake-backed driver, plus public signature/property parity.
- `tests/test_commands.py` and `tests/test_connection.py`: exact VISA commands,
  parsing, configuration, ownership, timeouts, and failure cleanup.
- `tests/conftest.py`: shared fixtures and pytest plugin registration.
- `tests/hardware.py`: pytest hardware options, guarded fixtures, restoration, and
  timing reports. `tests/test_hardware.py` contains the hardware tests, marked
  `hardware` and skipped unless --run-hardware is explicitly passed.
- `tests/test_hardware_runner.py`: isolated pytest sessions using fake resources
  to verify collection gating, option validation, failures, cleanup, and timing.
- `tests/test_cli.py`: example argument validation, dispatch, and cleanup with
  the simulator and fake hardware resources.
- `tests/test_numeric_validation.py`: finite numeric inputs, positive rounded
  scan speeds, state preservation, and invalid hardware scan-speed readback.
- `tests/test_timeouts.py`: configurable operation allowances, scan buffers,
  preservation of longer/infinite timeouts, and restoration failures.

Run the default suite without hardware:

```sh
uv run pytest -v
```

There is no CI configuration or configured formatter or linter. Choose
validation appropriate to the change. Basic checks that do not contact hardware are:

```sh
uv run python -m compileall -q src
uv run python examples/cli.py --virtual get_wavelength
uv run python examples/cli.py --help
git diff --check
```

The simulator's initial wavelength is `0` after connection. For behavioral changes, exercise
properties and methods in a single simulator instance, or use a fake VISA
resource/resource manager to check the hardware driver's commands, parsing,
timeouts, and cleanup. Simulator checks alone do not validate the wire protocol.
For packaging checks, run `uv build`; build outputs are ignored by Git.
The real-hardware suite is invoked with
`uv run pytest tests/test_hardware.py --run-hardware` and
explicit resource, wavelength, grating, turret, and filter arguments (see README).
It exercises all public commands and attempts state restoration after each test.
Use `-k test_turret_information` to isolate the reinstated `?TURRETS` command.
Do not skip its failures merely because that command previously had firmware issues.
Use `-k test_home_filter_timing` to measure homing from all six filter
positions, including home. `--home-repetitions` repeats the sweep and
`--filter-home-timeout-ms` overrides the tested homing allowance. This test uses
the exact allowance during FHOME so a longer general timeout cannot mask an
invalid estimate; it reports durations, headroom, and the slowest observation.
Homing positions and repeats have individual parametrised node IDs. Use
--visa-backend=@py (equals sign); pytest treats standalone @py as an argument
file. Hardware tests must run sequentially; parallel worker execution is rejected.
Neither default runs nor --collect-only may contact hardware.

## Change conventions

- Follow the existing four-space indentation, property-based API, and NumPy-style
  parameter/return docstrings. Document units explicitly.
- Preserve public imports, method signatures, and context-manager behavior
  unless the requested change requires an API change.
- For shared API changes, review the hardware driver, simulator, and example CLI
  dispatch. Both implementations expose `turret_info`; `?TURRETS` has
  historically had hardware issues, which the integration suite should expose.
  The simulator must match public signatures, connection-state errors, and numeric
  conversions/precision. Keep the shared contract current when the API changes.
- Preserve protocol details intentionally: writes terminate with `\r`, reads
  with ` ok\r\n`, and connection setup sends `NO-ECHO`. `_write`, `_query`,
  and `_read_bytes` check connection state; `_query` returns the unparsed PyVISA
  response and `_query_value` removes the leading space and unit.
  `_query_manual` reads one byte at a time to handle
  partial termination sequences. Use the module constants ENCODING,
  WRITE_TERMINATION, and READ_TERMINATION for setup and manual response parsing.
- The driver warns with UserWarning and discards overrides of termination,
  encoding, and fixed serial
  settings; RS232 uses 9600 baud, 8N1, and no flow control. Keep fixed-setting
  option handling consistent in both implementations. Delegate all other resource
  options to PyVISA open_resource; the simulator accepts and ignores these
  without attempting to duplicate backend validation. Resource class overrides
  also warn and are discarded so they cannot bypass serial configuration.
  The resource manager is
  keyword-only and retained by the PyVISA resource, but never closed by the driver
  because PyVISA shares manager sessions. Do not store a separate manager reference
  on the driver. Disconnect explicitly before reconnecting.
  The underlying VISA resource is private (`_instr`); callers use the driver API
  for commands and connection lifecycle.
- Wavelengths are in nm, scan speed is in nm/min, and VISA timeouts are in ms.
  Scanning uses `NM`, direct positioning uses `GOTO`, and numeric wavelength
  and scan-speed commands use one decimal place. Review temporary timeout
  restoration and resource cleanup when changing error handling.
  Both implementations reject nonfinite wavelength/scan-speed inputs and require
  scan speed to remain positive after rounding. Scanning also validates hardware
  scan-speed readback before calculating duration or changing the timeout.
  Operation allowances are configurable in ms: grating_timeout_ms (30000),
  filter_timeout_ms (10000), filter_home_timeout_ms (20000), and
  scan_timeout_buffer_ms (5000). Both implementations expose these attributes.
  Extend rather than shorten caller timeouts; restore after operations. Preserve
  an active command exception if restoration also fails, logging that failure.
- Keep fixes scoped; avoid unrelated packaging modernization or version bumps.
- Use the simulator or fake resources for routine validation. Real command-line
  operations connect to equipment and may move gratings or the filter wheel;
  only run them when hardware use is part of the authorized task.

## Development VM boundaries

This guest uses the host-managed network sandbox from the `dev-vm` repository.
Private and local IPv4 destinations are blocked by default. Before concluding
that networked hardware is down, consider that policy. Ask the user to run this
on the host from the `dev-vm` repository for the device's exact IPv4 address:

```sh
./manage-network-access.sh add <IPv4-address>
```

For a persistent exception, the user can add that exact address to
`SANDBOX_ALLOWED_IPV4_DESTINATIONS` in the host's `dev-vm/vm-config.sh`. The
guest cannot change or bypass host network policy.

Repositories under `/workspaces/projects` are private guest clones, not mounted
host working trees. The host cannot see uncommitted guest files, and the guest
does not have the host's upstream Git credentials. When returning work to the
host, commit intended changes and ensure the relevant repositories are clean.
If submodules are involved, commit the deepest changed submodule first, then
commit updated gitlinks outward through its parents. Tell the user to run this
from the host's `dev-vm` repository:

```sh
./pull-project-changes.sh <host-project-path>
```

When the user reports pushed host changes or asks to integrate `host/*` refs,
use the `integrate-host-changes` skill. Do not guess pending refs or discard
guest work. Project lifecycle scripts run on the host; do not run them in the
guest or bypass the private-clone boundary.

Agents run as the unprivileged `agent` account, with USB development access via
`dialout` and an account-owned rootless Docker daemon. There is no sudo or
rootful Docker socket access. Do not switch to the administrative `dev` account.
For necessary guest administration, explain the command and ask the user to
perform it through the host-managed update workflow or administrative SSH.
