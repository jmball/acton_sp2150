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
