"""Stateful VISA doubles that never open a backend or contact equipment."""

from pyvisa import constants
from pyvisa.resources import MessageBasedResource, SerialInstrument
from unittest.mock import Mock


def make_manager(resource):
    """Mock opening a resource and applying its connection options.

    Parameters
    ----------
    resource : pyvisa.resources.Resource
        Fake resource returned by the manager.

    Returns
    -------
    manager : unittest.mock.Mock
        Manager whose open_resource applies keyword options to the
        supplied resource.
    """
    manager = Mock()

    def open_resource(resource_name, access_mode=0, open_timeout=0, **options):
        for name, value in options.items():
            setattr(resource, name, value)
        return resource

    manager.open_resource.side_effect = open_resource
    return manager


class FakeResourceMixin:
    """Exercise real PyVISA descriptors and the driver's command parsing."""

    def __init__(self):
        self._session = None
        self.values = {constants.ResourceAttribute.timeout_value: 1000}
        self.commands = []
        self.close_count = 0
        self.fail_attribute = None
        self.fail_command = None
        self.fail_close = False
        self.scan_speed = 1000.0
        self.wavelength = 0.0
        self.grating = 1
        self.turret = 1
        self.filter = 1
        self.grating_info = "1: 1200 lines/mm, blaze 500 nm\r\n2: grating info"
        self.turret_info = "1: gratings 1, 2\r\n2: turret info"
        self._pending = b""

    def set_visa_attribute(self, name, value):
        if name == self.fail_attribute:
            raise ValueError("attribute rejected")
        self.values[name] = value
        return constants.StatusCode.success

    def get_visa_attribute(self, name):
        return self.values[name]

    def query(self, command):
        self.commands.append(command)
        if command == self.fail_command:
            raise TimeoutError("query failed")
        queries = {
            "?NM/MIN": ("scan_speed", "nm/min"),
            "?NM": ("wavelength", "nm"),
            "?GRATING": ("grating", ""),
            "?TURRET": ("turret", ""),
            "?FILTER": ("filter", ""),
        }
        if command in queries:
            name, unit = queries[command]
            return f" {getattr(self, name)} {unit}"
        if command == "NO-ECHO":
            return ""
        if command == "FHOME":
            self.filter = 1
            return ""
        value, operation = command.split()
        setters = {
            "NM/MIN": ("scan_speed", float),
            "NM": ("wavelength", float),
            "GOTO": ("wavelength", float),
            "GRATING": ("grating", int),
            "TURRET": ("turret", int),
            "FILTER": ("filter", int),
        }
        name, convert = setters[operation]
        setattr(self, name, convert(value))
        return ""

    def write(self, command):
        self.commands.append(command)
        if command == self.fail_command:
            raise TimeoutError("query failed")
        info = {"?GRATINGS": self.grating_info, "?TURRETS": self.turret_info}[command]
        self._pending = f" {info} ok\r\n".encode("ASCII")
        return len(command)

    def read_bytes(self, count):
        if len(self._pending) < count:
            raise TimeoutError("incomplete response")
        response, self._pending = self._pending[:count], self._pending[count:]
        return response

    def close(self):
        self.close_count += 1
        if self.fail_close:
            raise OSError("close failed")


class FakeSerial(FakeResourceMixin, SerialInstrument):
    pass


class FakeMessage(FakeResourceMixin, MessageBasedResource):
    pass
