# Repository guide

## Purpose and layout

This repository controls a Princeton Instruments Acton SP-2150 monochromator
and FA-2448 filter wheel.

- `src/sp2150/sp2150.py`: PyVISA hardware driver and argparse command-line example.
- `src/virtual_sp2150/virtual_sp2150.py`: in-memory simulator with a similar API
  and its own command-line example; it does not emulate VISA communication.
- Both packages export a lowercase `sp2150` class through `__init__.py` and
  obtain `__version__` using `importlib.metadata` and the distribution name
  `acton_sp2150`, falling back to `0.0.0` when it is not installed.
- `pyproject.toml`: Hatchling build configuration, package metadata, version,
  dependency declarations, and explicit `src` package inclusion.
  The distribution name is `acton_sp2150`; import names are
  `sp2150` and `virtual_sp2150`.

## Development and validation

Use an isolated environment and install the project from the repository root:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e .
```

Runtime dependencies are `pyvisa` and `pyvisa-py`. Hardware access also needs a
working VISA backend and the dependencies appropriate to the connection type.
The package requires Python >=3.8, matching the hardware driver's use of a
walrus operator. Preserve that minimum when changing syntax or dependencies.

There is no committed test suite, CI configuration, or configured formatter or
linter. Choose validation appropriate to the change; do not claim a full test
suite passed. Basic checks that do not contact hardware are:

```sh
.venv/bin/python -m compileall -q src
.venv/bin/python src/virtual_sp2150/virtual_sp2150.py get_wavelength
.venv/bin/python src/virtual_sp2150/virtual_sp2150.py --help
.venv/bin/python src/sp2150/sp2150.py --help
git diff --check
```

The simulator's initial wavelength is `0`. For behavioral changes, exercise
properties and methods in a single simulator instance, or use a fake VISA
resource/resource manager to check the hardware driver's commands, parsing,
timeouts, and cleanup. Simulator checks alone do not validate the wire protocol.
If a packaging check is needed, install `build` in the environment and run
`.venv/bin/python -m build`; build outputs are ignored by Git.

## Change conventions

- Follow the existing four-space indentation, property-based API, and NumPy-style
  parameter/return docstrings. Document units explicitly.
- Preserve public imports, method signatures, and context-manager behavior
  unless the requested change requires an API change.
- For shared API changes, review the hardware driver, simulator, and both CLI
  dispatch blocks. The simulator currently accepts values without the hardware
  driver's numeric coercion and implements `turret_info`, which is disabled in
  the hardware driver because `?TURRETS` was not recognized.
- Preserve protocol details intentionally: writes terminate with `\r`, reads
  with ` ok\r\n`, connection setup sends `NO-ECHO`, and `_query` removes the
  leading space and unit. `_query_manual` reads one byte at a time to handle
  partial termination sequences.
- Wavelengths are in nm, scan speed is in nm/min, and VISA timeouts are in ms.
  Scanning uses `NM`, direct positioning uses `GOTO`, and numeric wavelength
  and scan-speed commands use one decimal place. Review temporary timeout
  restoration and resource cleanup when changing error handling.
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
