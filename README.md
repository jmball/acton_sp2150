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

Run hardware tests against a connected instrument:

```sh
uv run pytest tests/test_hardware.py \
  --resource-name 'ASRL2::INSTR' --visa-backend=@py
```

See [tests/test_hardware.py](tests/test_hardware.py) for optional settings.

## License

See [LICENSE](LICENSE).
