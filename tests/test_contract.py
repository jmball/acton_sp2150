"""Public API parity and shared pytest command contract."""

import inspect
import pytest

from sp2150 import sp2150
from virtual_sp2150 import sp2150 as virtual_sp2150
from tests.contract import (
    test_scan_speed, test_direct_wavelength, test_scanned_wavelength, test_grating,
    test_turret, test_filter, test_home_filter, test_grating_information,
    test_turret_information,
)


def test_public_members_and_signatures_match():

    def public_members(driver):
        return {
            name: member for name,
            member in inspect.getmembers(
                driver
            ) if not name.startswith(
                '_'
            ) and (
                inspect.isfunction(
                    member
                ) or isinstance(
                    member,
                    property
                )
            )
        }
    actual = public_members(sp2150)
    simulated = public_members(virtual_sp2150)
    assert actual.keys() == simulated.keys()
    for name, member in actual.items():
        other = simulated[name]
        if isinstance(member, property):
            assert isinstance(other, property)
            for accessor in ('fget', 'fset', 'fdel'):
                first, second = (getattr(member, accessor), getattr(other, accessor))
                assert (first is None) == (second is None)
                if first is not None:
                    assert inspect.signature(first) == inspect.signature(second)
        else:
            assert inspect.signature(member) == inspect.signature(other)


def test_context_manager_signatures_match():
    for name in ('__init__', '__enter__', '__exit__'):
        assert inspect.signature(
            getattr(
                sp2150,
                name
            )
        ) == inspect.signature(
            getattr(
                virtual_sp2150,
                name
            )
        )


def test_disconnected_operations_match():
    for driver in (sp2150, virtual_sp2150):
        device = driver()
        for name in (
            'scan_speed',
            'wavelength',
            'grating',
            'turret',
            'filter',
            'grating_info',
            'turret_info'
        ):
            with pytest.raises(RuntimeError, match='not connected'):
                getattr(device, name)
        for name in ('scan_speed', 'wavelength', 'grating', 'turret', 'filter'):
            with pytest.raises(RuntimeError, match='not connected'):
                setattr(device, name, 1)
        with pytest.raises(RuntimeError, match='not connected'):
            device.scan_to_wavelength(500)
        with pytest.raises(RuntimeError, match='not connected'):
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
    _VALIDATION_CASES.append(pytest.param(
        operation, valid_value, None, expected_value, id=f"{operation}-valid",
    ))
    integer_operation = operation in ("grating", "turret", "filter")
    for value, label in (("bad", "invalid-string"), (float("nan"), "nan"),
                         (float("inf"), "infinity"), (float("-inf"), "negative-infinity")):
        error_type = OverflowError if integer_operation and label.endswith("infinity") else ValueError
        _VALIDATION_CASES.append(pytest.param(
            operation, value, error_type, None, id=f"{operation}-{label}",
        ))
for value, label in ((0, "zero"), (-1, "negative"), (0.01, "rounded-zero")):
    _VALIDATION_CASES.append(pytest.param(
        "scan_speed", value, ValueError, None, id=f"scan_speed-{label}",
    ))


@pytest.mark.parametrize("connected", [True, False], ids=["connected", "disconnected"])
@pytest.mark.parametrize("operation,value,error_type,expected_value", _VALIDATION_CASES)
def test_argument_validation_precedes_connection_check(
    instrument, resource, manager, connected, operation, value, error_type, expected_value,
):
    names = ("scan_speed", "wavelength", "grating", "turret", "filter")
    initial_state = {name: getattr(instrument, name) for name in names}
    if not connected:
        instrument.disconnect()
    resource.commands.clear()
    expected_error = error_type if error_type is not None else (None if connected else RuntimeError)

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
        match = "Instrument is not connected" if expected_error is RuntimeError else None
        with pytest.raises(expected_error, match=match):
            invoke()
        assert resource.commands == []
        if not connected:
            instrument.connect("fake", resource_manager=manager)
        assert {name: getattr(instrument, name) for name in names} == initial_state
