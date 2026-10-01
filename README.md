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
uv run python examples/cli.py --virtual get_wavelength
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

The command-line example uses hardware by default and requires a resource name:

```sh
uv run python examples/cli.py --resource-name 'ASRL2::INSTR' --visa-backend '@py' get_wavelength
uv run python examples/cli.py --virtual goto_wavelength --parameter 532
uv run python examples/cli.py --help
```

Commands that set values or scan require `--parameter`; getters and `home_filter`
do not accept it. Wavelengths are in nm, scan speed in nm/min, and timeouts in ms.
Each invocation connects, runs one command, and disconnects. A new simulator
starts with wavelength 0 on each invocation. Hardware invocations may move the
instrument. Serial access with `@py` requires pyserial, for example via
`uv run --with pyserial python examples/cli.py ...`.

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

Both implementations reject nonfinite wavelength and scan-speed inputs with
`ValueError`. Scan speed must remain positive after rounding to one decimal place
(for example, `0.01` nm/min is rejected because it rounds to zero). Invalid inputs
do not send commands or change state. Before scanning, the hardware driver also
requires a finite, positive scan speed read back from the instrument.

Operation timeout allowances are configurable attributes in milliseconds:

| Attribute | Default | Operation |
| --- | ---: | --- |
| `grating_timeout_ms` | 30000 | Grating selection |
| `filter_timeout_ms` | 10000 | Filter selection |
| `filter_home_timeout_ms` | 20000 | Filter homing |
| `scan_timeout_buffer_ms` | 5000 | Added to calculated wavelength scan duration |

Grating indexing takes approximately 20 seconds according to the
[SP-2150i manual](https://www.princetoninstruments.com/wp-content/uploads/2020/04/SP-2150i.pdf).
The [FA-2448 manual](https://cfd.rit.edu/products/manuals/Princeton%20Acton/FA-2448.pdf)
specifies 2.5 seconds per adjacent filter position, with selection taking the
shortest route. The defaults include additional allowance. Filter homing has no
documented duration; its default conservatively allows a full revolution plus
margin and should be checked against your hardware.

For example, set `mono.grating_timeout_ms = 40000` or
`mono.scan_timeout_buffer_ms = 10000` before running an operation. A scan's
timeout is calculated from the current wavelength and scan speed plus the buffer.
These operations temporarily extend the resource timeout when needed and restore
the previous setting afterward, including when a command fails. A longer or
infinite caller timeout is preserved. Allowances must be finite and nonnegative;
zero disables the fixed-operation extension or removes the scan buffer.
The simulator exposes the same attributes, with immediate simulated operations.

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
The hardware suite also includes `test_home_filter_timing`: it positions the wheel
at each of positions 1 through 6 (including home), then times `FHOME` alone using
a monotonic clock and checks the final position. It reports each elapsed time,
remaining headroom in seconds and percent, and the slowest observed case.
During homing this test applies the driver's homing allowance exactly, even when
the general `--timeout` is longer, then restores the previous resource timeout.
Timeouts, an exceeded allowance, and incorrect final positions fail the test.

To isolate this measurement and repeat the sweep three times:

```sh
uv run python -m tests.hardware \
  --resource-name 'ASRL2::INSTR' --visa-backend '@py' \
  --wavelength 500 --scan-wavelength 501 --turret 1 --grating 1 \
  --filter-position 2 --test test_home_filter_timing --home-repetitions 3
```

Use `--filter-home-timeout-ms 30000` to measure against a different allowance;
the default follows `filter_home_timeout_ms` from the driver (currently 20000 ms).
The timing covers communication and command completion, excluding positioning
and the subsequent position query. The test attempts to restore the original
instrument state afterward. Passing establishes the observed timing margin for
your hardware and tested starting positions; it does not establish a universal
worst-case duration.

`--visa-backend` can be omitted to use the system-selected backend. Backend
dependencies must be installed; for serial communication with `@py`, include
pyserial with `uv run --with pyserial python -m tests.hardware ...`.

Add `--test test_turret_information` to the complete command above to isolate
`?TURRETS`, or repeat `--test` to select multiple tests. An unsupported command
is reported as an ordinary failure/error, so the hardware result remains visible.
Run `uv run python -m tests.hardware --help` for all CLI options. Tests have been
validated against fake resources; actual hardware results depend on the connected
instrument and its firmware.
