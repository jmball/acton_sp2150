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
Passing any of these fixed settings, including matching values, raises
`ValueError`. Unknown, read-only, or unsupported resource options raise
`TypeError`; valid writable VISA settings remain configurable. `access_mode`
and `open_timeout` are forwarded when opening the resource. `resource_pyclass`
overrides are not supported: PyVISA selects the interface from the resource name.

Initialization failures close the partially configured session and leave the
driver disconnected. Calling `connect()` while connected raises `RuntimeError`;
call `disconnect()` first to reconnect. Disconnecting repeatedly is safe and
clears connection state even if closing fails. The driver retains its resource
manager while connected but closes only its instrument session, since PyVISA
shares managers between callers. Supplied managers remain caller-owned; default
managers follow PyVISA's shared lifetime. Context cleanup preserves an exception
already raised by the body and logs any additional close failure.

The simulator accepts the same keyword-only manager and validates resource
options without opening hardware. It supports the same explicit reconnect
behavior and converts numeric setters to the hardware driver's numeric types;
its in-memory properties remain usable without connecting.

Run the hardware-free regression tests with:

```sh
uv run python -m unittest discover -s tests -v
```
