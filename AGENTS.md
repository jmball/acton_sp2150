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

Runtime dependencies are `pyvisa` and `pyvisa-py[serial]`; the serial extra
installs PySerial. Hardware access also needs a
working VISA backend and the dependencies appropriate to the connection type.
The package requires Python >=3.10. Preserve that minimum when changing syntax
or dependencies. Use `uv run` for project commands, `uv add`/`uv remove` for
dependency changes, and `uv lock` after editing dependency declarations by hand.
Commit `uv.lock` updates alongside the corresponding `pyproject.toml` changes.
Use setuptools as the build backend; do not introduce Hatchling.

Tests use native pytest functions, fixtures, and parametrisation. Pytest is a
locked development dependency. Keep test configuration in pyproject.toml:

- `tests/test_api.py`: public signatures, shared numeric validation and precision,
  disconnected behavior, fixed-option parity, and commands imported from the
  reusable `tests/contract.py` contract for simulator/fake/hardware coverage.
- `tests/test_driver.py`: fake-backed connection setup, ownership, cleanup, exact
  wire commands, parsing, timeouts, and invalid device readback.
- `tests/test_virtual.py`: simulator state, lifecycle, backend independence, and
  simulated experiments.
- `tests/test_cli.py`: example argument validation, dispatch, and cleanup.
- `tests/test_hardware.py`: real command contract and homing timings; skipped
  unless --resource-name is supplied. Optional settings are documented there.
- `tests/hardware_plugin.py`: hardware options, guarded fixtures, state restoration,
  and timing reports. `tests/test_hardware_plugin.py` tests it in isolated pytest
  sessions with fake resources, including gating, errors, cleanup, and timing.
- `tests/conftest.py`: shared fixtures and plugin registration.
- `tests/fakes.py`: VISA resources and manager doubles used without hardware.

Run the default suite without hardware:

```sh
uv run pytest -v
```

Always use ty for type checking and Ruff for linting and formatting. Both are
locked development dependencies configured in pyproject.toml; do not introduce
alternative type checkers, linters, or formatters. Both tools infer the minimum
Python version from project.requires-python. Before completing Python changes, run:

```sh
uv run ty check
uv run ruff check .
uv run ruff format --check .
```

Use `uv run ruff check --fix .` for automatic lint fixes and `uv run ruff format .`
to format code. Check source, examples, and tests; keep suppressions narrow and
explain any intentional exceptions. There is no CI configuration. Other basic
checks that do not contact hardware are:

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
`uv run pytest tests/test_hardware.py --resource-name <VISA-name>`.
Hardware defaults select grating 1 and turret 1. Wavelength, scan speed, grating,
turret, and filter settings have optional CLI overrides documented in
tests/test_hardware.py; keep these details out of README.
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
Before the first real hardware test session, remind the user to inspect and save
raw `?GRATINGS` and `?TURRETS` responses, including formatting and terminators.
Use those captures with the manual to determine a justified maximum response
length. Keep the manual reader's existing per-character resource timeout; do
not introduce an overall deadline or guessed response-size limit.

## Change conventions

- Keep README concise: installation, editable installation, examples, testing,
  and an optional link to LICENSE. Do not duplicate dependency versions, license
  text, API details, or repository decision history there. Code and docstrings
  are the main API documentation.
- Follow the existing four-space indentation, property-based API, and NumPy-style
  parameter/return docstrings. Document units explicitly.
  Include Parameters for arguments other than self/cls and Returns for meaningful
  return values; omit empty sections for methods returning None. Use Yields for
  generators and Attributes for configurable instance fields. Name entries in
  Returns and Yields using `name : type`. Do not use Raises
  sections. Prefer concise descriptive prose over Notes headings.
- Preserve public imports, method signatures, and context-manager behavior
  unless the requested change requires an API change.
- For shared API changes, review the hardware driver, simulator, and example CLI
  dispatch. Both implementations expose `turret_info`; `?TURRETS` has
  historically had hardware issues, which the integration suite should expose.
  The simulator must match public signatures, connection-state errors, and numeric
  conversions/precision. Keep the shared contract current when the API changes.
  Validate numeric command arguments before checking connection state in both
  implementations. Invalid inputs retain their validation errors when disconnected;
  valid inputs require an active connection. Rejected arguments and disconnected
  operations must preserve state.
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
  and scan-speed commands use one decimal place. The manual specifies 0.1 nm
  wavelength positioning; one-decimal scan speed is a driver convention whose
  device resolution still needs confirmation. Use round(value, 1) for numeric
  rounding and formatting only to construct command strings or display text.
  Review temporary timeout
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
