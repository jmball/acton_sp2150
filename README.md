# acton_sp2150
Control a Princeton Instruments Acton SP-2150 monochromator with FA-2448 filter wheel

Requires Python 3.8 or newer. Install from the repository root:

```sh
python3 -m pip install .
```

For development, use a virtual environment and an editable installation:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e .
```

If your Python installation does not provide `venv`, you can instead create the
environment with `uv venv .venv` and install with `uv pip install -e .`.

The distribution includes the `sp2150` hardware driver and the
`virtual_sp2150` simulator. Hardware access requires a working VISA backend;
the simulator can be used without connecting to an instrument.

To build a source distribution and wheel:

```sh
.venv/bin/python -m pip install build
.venv/bin/python -m build
```
