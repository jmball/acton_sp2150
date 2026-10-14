# acton_sp2150

Control a Princeton Instruments Acton SP-2150 monochromator and FA-2448 filter wheel.

## Installation

From the repository root:

```sh
uv venv
uv pip install .
```

## Editable installation

Install the project and development dependencies:

```sh
uv sync --locked
```

## Examples

See [examples/](examples/) for usage examples. The API is documented in the code
and its docstrings.

```sh
uv run python examples/cli.py --virtual get_wavelength
uv run python examples/cli.py --help
```

## Testing

Run the tests without hardware:

```sh
uv run pytest
```

Hardware tests require a connected instrument and valid targets:

```sh
uv run --with pyserial pytest tests/test_hardware.py --run-hardware \
  --resource-name 'ASRL2::INSTR' --visa-backend=@py \
  --wavelength 500 --scan-wavelength 501 \
  --turret 1 --grating 1 --filter-position 2
```

Run `uv run pytest --help` for test options.

## License

See [LICENSE](LICENSE).
