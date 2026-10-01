# acton_sp2150
Control a Princeton Instruments Acton SP-2150 monochromator with FA-2448 filter wheel

Requires Python 3.10 or newer. Use uv for development, installation, and builds.
From the repository root:

```sh
uv sync --locked
```

This creates `.venv` and installs the project in editable mode with the
dependencies pinned in `uv.lock`. Run commands through uv:

```sh
uv run python src/virtual_sp2150/virtual_sp2150.py get_wavelength
```

After changing dependencies in `pyproject.toml`, run `uv lock` and commit the
updated lockfile. To install into a separate virtual environment instead of
using the development environment:

```sh
uv venv /path/to/venv
uv pip install --python /path/to/venv/bin/python .
```

The distribution includes the `sp2150` hardware driver and the
`virtual_sp2150` simulator. Hardware access requires a working VISA backend;
the simulator can be used without connecting to an instrument.

To build a source distribution and wheel:

```sh
uv build
```

Licensed under MIT; see [LICENSE](LICENSE). Package metadata uses the same MIT
license and includes the license file in distributions.

Connections accept a VISA resource name and a keyword-only resource manager:

```python
import pyvisa
from sp2150 import sp2150

with pyvisa.ResourceManager("@py") as manager:
    with sp2150() as mono:
        mono.connect("ASRL2::INSTR", resource_manager=manager, timeout=30000)
        print(mono.wavelength)
```

The driver manages ASCII encoding, write termination `\r`, and read termination
` ok\r\n`. For serial resources it also sets 9600 baud, 8 data bits, no parity,
one stop bit, and no flow control. The framing requirements are documented in
the [SP-2150i operating instructions, section IV-B](https://www.princetoninstruments.com/wp-content/uploads/2020/04/SP-2150i.pdf).
Passing any of these fixed settings, including matching values, emits a
`UserWarning` and ignores the override. Other resource options are passed directly
to PyVISA's
`open_resource()` for validation and application; accepted options and errors
follow PyVISA and the selected backend. `resource_pyclass`
overrides also warn and are ignored: PyVISA selects the interface from the
resource name.
For serial resources, `end_input` stops reads at the final newline and
`end_output` disables extra backend termination; these settings work with the
driver's read and write termination strings.

Failures during driver initialization after PyVISA returns a resource close that
session and leave the driver disconnected. Failures within `open_resource()` use
PyVISA's own cleanup. Calling `connect()` while connected raises `RuntimeError`;
call `disconnect()` first to reconnect. Disconnecting repeatedly is safe and
clears connection state even if closing fails. The PyVISA resource retains its
manager; the driver closes only its instrument session, since PyVISA shares
managers between callers. Supplied managers remain caller-owned; default
managers follow PyVISA's shared lifetime. Context cleanup preserves an exception
already raised by the body and logs any additional close failure.

The simulator accepts the same keyword-only manager and warns and ignores fixed
device overrides without opening hardware. Other backend options are accepted and
ignored; the simulator does not reproduce PyVISA option validation errors.
It supports the same explicit reconnect
behavior and converts numeric setters to the hardware driver's numeric types;
operations require `connect()` just as they do with the hardware driver.
Wavelength and scan speed use the same one-decimal precision, and state persists
across disconnect/reconnect. Simulation uses immediate in-memory state changes;
it does not emulate movement time, hardware faults, or installed grating limits.

The test suite has three complementary layers:

- Simulator state tests and a shared API contract check experiment behavior,
  matching signatures, property access, numeric conversions, and connection state.
- Fake VISA resources check exact wire commands, parsing, timeouts, configuration,
  and failure cleanup. The shared contract also runs against the fake-backed driver.
- The explicit hardware runner applies the same command contract to an attached
  instrument, including `?GRATINGS`, the reinstated `?TURRETS`, scanning, direct
  positioning, grating/turret selection, filter positioning, and filter homing.

Run all hardware-free tests (the default discovery never contacts hardware):

```sh
uv run python -m unittest discover -s tests -t . -v
```

Run the hardware suite explicitly with targets valid for your instrument:

```sh
uv run python -m tests.hardware \
  --resource-name 'ASRL2::INSTR' --visa-backend '@py' --timeout 30000 \
  --wavelength 500 --scan-wavelength 501 --scan-speed 600 \
  --turret 1 --grating 1 --filter-position 2
```

The runner moves the instrument. It requires explicit wavelength targets and
installed grating, turret, and filter positions. Before each test it reads the
initial settings; afterward it attempts to restore turret, grating, scan speed,
wavelength, and filter position, then disconnects and closes its own manager.
Restoration failures are reported and the remaining cleanup steps still run.

Use `--resource-option 'query_delay=0.05'` for additional connection options
(`KEY=JSON`, repeatable), or `--resource-option 'open_timeout=2000'` for opening
options. Fixed device settings warn and are ignored. The expected filter home
position defaults to 1 and can be set with `--home-filter-position`.
`--visa-backend` can be omitted to use the system-selected backend. Backend
dependencies must be installed; for serial communication with `@py`, include
pyserial with `uv run --with pyserial python -m tests.hardware ...`.

Add `--test test_turret_information` to the complete command above to isolate
`?TURRETS`, or repeat `--test` to select multiple tests. An unsupported command
is reported as an ordinary failure/error, so the hardware result remains visible.
Run `uv run python -m tests.hardware --help` for all CLI options. Tests have been
validated against fake resources; actual hardware results depend on the connected
instrument and its firmware.
