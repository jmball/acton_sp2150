"""Shared commands, public API parity, validation, and numeric precision."""

import inspect

import pytest
from pyvisa import constants

from sp2150 import sp2150
from virtual_sp2150 import sp2150 as virtual_sp2150
from tests.contract import (
    test_scan_speed,
    test_direct_wavelength,
    test_scanned_wavelength,
    test_grating,
    test_turret,
    test_filter,
    test_home_filter,
    test_grating_information,
    test_turret_information,
)


def test_public_members_and_signatures_match():

    def public_members(driver):
        return {
            name: member
            for name, member in inspect.getmembers(driver)
            if not name.startswith("_")
            and (inspect.isfunction(member) or isinstance(member, property))
        }

    actual = public_members(sp2150)
    simulated = public_members(virtual_sp2150)
    assert actual.keys() == simulated.keys()
    for name, member in actual.items():
        other = simulated[name]
        if isinstance(member, property):
            assert isinstance(other, property)
            for accessor in ("fget", "fset", "fdel"):
                first, second = (getattr(member, accessor), getattr(other, accessor))
                assert (first is None) == (second is None)
                if first is not None:
                    assert inspect.signature(first) == inspect.signature(second)
        else:
            assert inspect.signature(member) == inspect.signature(other)


def test_context_manager_signatures_match():
    for name in ("__init__", "__enter__", "__exit__"):
        assert inspect.signature(getattr(sp2150, name)) == inspect.signature(
            getattr(virtual_sp2150, name)
        )


def test_disconnected_readers_and_homing_match():
    for driver in (sp2150, virtual_sp2150):
        device = driver()
        for name in (
            "scan_speed",
            "wavelength",
            "grating",
            "turret",
            "filter",
            "grating_info",
            "turret_info",
        ):
            with pytest.raises(RuntimeError, match="not connected"):
                getattr(device, name)
        with pytest.raises(RuntimeError, match="not connected"):
            device.home_filter()


_VALIDATION_CASES = []


for operation, valid_value, expected_value in (
    ("scan_speed", "123.46", 123.5),
    ("wavelength", "532.26", 532.3),
    ("scan_to_wavelength", "532.26", 532.3),
    ("grating", "2", 2),
    ("turret", "2", 2),
    ("filter", "3", 3),
):
    _VALIDATION_CASES.append(
        pytest.param(
            operation, valid_value, None, expected_value, id=f"{operation}-valid"
        )
    )
    integer_operation = operation in ("grating", "turret", "filter")
    for value, label in (
        ("bad", "invalid-string"),
        (float("nan"), "nan"),
        (float("inf"), "infinity"),
        (float("-inf"), "negative-infinity"),
    ):
        error_type = (
            OverflowError
            if integer_operation and label.endswith("infinity")
            else ValueError
        )
        _VALIDATION_CASES.append(
            pytest.param(operation, value, error_type, None, id=f"{operation}-{label}")
        )


for value, label in ((0, "zero"), (-1, "negative"), (0.01, "rounded-zero")):
    _VALIDATION_CASES.append(
        pytest.param("scan_speed", value, ValueError, None, id=f"scan_speed-{label}")
    )


for value, label in (
    (-0.01, "negative-small"),
    (0.049, "rounded-boundary"),
    ("0", "zero-string"),
    ("0.01", "rounded-zero-string"),
):
    _VALIDATION_CASES.append(
        pytest.param("scan_speed", value, ValueError, None, id=f"scan_speed-{label}")
    )


for operation in ("scan_speed", "wavelength", "scan_to_wavelength"):
    for value, label in (
        ("nan", "nan-string"),
        ("inf", "infinity-string"),
        ("-inf", "negative-infinity-string"),
    ):
        _VALIDATION_CASES.append(
            pytest.param(operation, value, ValueError, None, id=f"{operation}-{label}")
        )


@pytest.mark.parametrize("connected", [True, False], ids=["connected", "disconnected"])
@pytest.mark.parametrize("operation,value,error_type,expected_value", _VALIDATION_CASES)
def test_argument_validation_precedes_connection_check(
    instrument,
    resource,
    manager,
    connected,
    operation,
    value,
    error_type,
    expected_value,
):
    names = ("scan_speed", "wavelength", "grating", "turret", "filter")
    initial_state = {name: getattr(instrument, name) for name in names}
    if not connected:
        instrument.disconnect()
    resource.commands.clear()
    expected_error = (
        error_type if error_type is not None else None if connected else RuntimeError
    )

    def invoke():
        if operation == "scan_to_wavelength":
            instrument.scan_to_wavelength(value)
        else:
            setattr(instrument, operation, value)

    if expected_error is None:
        invoke()
        property_name = "wavelength" if operation == "scan_to_wavelength" else operation
        assert getattr(instrument, property_name) == expected_value
    else:
        match = (
            "Instrument is not connected" if expected_error is RuntimeError else None
        )
        with pytest.raises(expected_error, match=match):
            invoke()
        assert resource.commands == []
        if not connected:
            instrument.connect("fake", resource_manager=manager)
        assert {name: getattr(instrument, name) for name in names} == initial_state


@pytest.mark.parametrize("driver", (sp2150, virtual_sp2150))
def test_manager_is_keyword_only_in_both_drivers(manager, driver):
    with pytest.raises(TypeError):
        driver().connect("ASRL2::INSTR", manager)


@pytest.mark.parametrize(
    "name,value",
    list(
        {
            "read_termination": " ok\r\n",
            "write_termination": "\r",
            "encoding": "ASCII",
            "baud_rate": 9600,
            "data_bits": 8,
            "parity": constants.Parity.none,
            "stop_bits": constants.StopBits.one,
            "flow_control": constants.ControlFlow.none,
            "end_input": constants.SerialTermination.termination_char,
            "end_output": constants.SerialTermination.none,
        }.items()
    ),
)
def test_fixed_options_warn_and_are_ignored_even_when_matching_defaults(
    connect, manager, resource, unconnected_driver, name, value
):
    with pytest.warns(UserWarning, match=name):
        connect(**{name: value})
    manager.open_resource.assert_called_with("serial-alias")
    assert unconnected_driver._instr is resource
    unconnected_driver.disconnect()
    simulator = virtual_sp2150()
    with pytest.warns(UserWarning, match=name):
        simulator.connect("dummy", **{name: value})
    assert simulator.wavelength == 0.0
    simulator.disconnect()


@pytest.mark.parametrize(
    "name,value",
    (
        ("grating_timeout_ms", 30000),
        ("filter_timeout_ms", 10000),
        ("filter_home_timeout_ms", 20000),
        ("scan_timeout_buffer_ms", 5000),
    ),
)
def test_defaults_match_simulator_and_instances_are_independent(
    connected_driver, name, value
):
    simulated = virtual_sp2150()
    assert getattr(connected_driver, name) == value
    assert getattr(simulated, name) == value
    setattr(connected_driver, name, value + 1)
    assert getattr(simulated, name) == value


def test_valid_values_retain_driver_precision(instrument):
    for value, expected in (("0.06", 0.1), (123.46, 123.5)):
        instrument.scan_speed = value
        assert instrument.scan_speed == expected
    instrument.wavelength = "532.26"
    assert instrument.wavelength == 532.3
    instrument.scan_to_wavelength("0")
    assert instrument.wavelength == 0.0
