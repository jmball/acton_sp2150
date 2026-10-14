"""Shared pytest fixtures; ordinary tests never construct a real VISA manager."""

import pytest

from sp2150 import sp2150
from virtual_sp2150 import sp2150 as virtual_sp2150
from tests.fakes import FakeSerial, make_manager
from tests.contract import ContractTargets

pytest_plugins = ["tests.hardware_plugin", "pytester"]


@pytest.fixture
def resource():
    return FakeSerial()


@pytest.fixture
def manager(resource):
    return make_manager(resource)


@pytest.fixture
def unconnected_driver():
    device = sp2150()
    yield device
    device.disconnect()


@pytest.fixture
def connect(unconnected_driver, manager):
    def connect_device(**options):
        unconnected_driver.connect("serial-alias", resource_manager=manager, **options)

    return connect_device


@pytest.fixture
def connected_driver(unconnected_driver, manager, resource):
    unconnected_driver.connect("fake", resource_manager=manager)
    # Command assertions begin after initialization; connection tests use connect.
    resource.commands.clear()
    return unconnected_driver


@pytest.fixture
def virtual_device():
    device = virtual_sp2150()
    device.connect("virtual")
    yield device
    device.disconnect()


@pytest.fixture(params=["virtual", "fake"])
def instrument(request):
    return request.getfixturevalue(
        "virtual_device" if request.param == "virtual" else "connected_driver"
    )


@pytest.fixture
def targets():
    return ContractTargets()
