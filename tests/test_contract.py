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
