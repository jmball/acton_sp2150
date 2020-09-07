"""Acton SP2150 monochromator control library."""


class sp2150:
    """Monochromator instrument object."""

    def __init__(self):
        """Initialise with dummy parameters."""
        self._scan_speed = 1000
        self._wavelength = 0
        self._grating = 1
        self._turret = 1
        self._grating_info = "dummy info"
        self._turret_info = "dummy info"
        self._filter = 1

    def __enter__(self):
        """Enter the runtime context related to this object."""
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        """Exit the runtime context related to this object."""
        self.disconnect()

    def connect(self, resource_name, resource_manager=None, **resource_kwargs):
        """Connect to the instrument.

        Parameters
        ----------
        resource_name : str
            Full VISA resource name, e.g. "ASRL2::INSTR", "GPIB0::14::INSTR" etc. See
            https://pyvisa.readthedocs.io/en/latest/introduction/names.html for more
            info on correct formatting for resource names.
        resource_manager : visa.ResourceManager, optional
            Resource manager used to create new connection. If `None`, create a new
            resource manager using system set VISA backend.
        resource_kwargs : dict
            Keyword arguments passed to PyVISA resource to be used to change
            instrument attributes after construction.
        """
        pass

    def disconnect(self):
        """Disconnect instrument."""
        pass

    def _setter_query(self, cmd):
        """Send a command to set a value and validate output.

        Paramters
        ---------
        cmd : str
            Command to issue.
        """
        pass

    @property
    def scan_speed(self):
        """Get grating scan speed in nm/min."""
        return self._scan_speed

    @scan_speed.setter
    def scan_speed(self, speed):
        """Set grating scan speed in nm/min."""
        self._scan_speed = speed

    def scan_to_wavelength(self, wavelength):
        """Scan grating to wavelength in nm."""
        self._wavelength = wavelength

    @property
    def wavelength(self):
        """Get current grating wavelength position in nm."""
        return self._wavelength

    @wavelength.setter
    def wavelength(self, wavelength):
        """Set grating position for wavelength in nm."""
        self._wavelength = wavelength

    @property
    def grating(self):
        """Get grating number."""
        return self._grating

    @grating.setter
    def grating(self, grating):
        """Set grating number."""
        self._grating = grating

    @property
    def turret(self):
        """Get turret number."""
        return self._turret

    @turret.setter
    def turret(self, turret):
        """Set turrent number."""
        self._turret = turret

    @property
    def grating_info(self):
        """Get groove spacing and blaze wavelength of each grating."""
        return self._grating_info

    @property
    def turret_info(self):
        """Get groove spacing of each grating on each turret."""
        return self._turret_info

    @property
    def filter(self):
        """Get filter wheel position number."""
        return self._filter

    @filter.setter
    def filter(self, filter_pos):
        """Set filter wheel position number."""
        self._filter = filter_pos

    def home_filter(self):
        """Set filter wheel to home position."""
        self._filter = 1


if __name__ == "__main__":
    import argparse

    # set up cli
    parser = argparse.ArgumentParser()
    parser.add_argument("-n", "--resource-name", help="Instrument resource name")
    parser.add_argument(
        "function",
        help="function to call",
        choices=[
            "set_scan_speed",
            "get_scan_speed",
            "scan_to_wavelength",
            "goto_wavelength",
            "get_wavelength",
            "set_grating",
            "get_grating",
            "set_turret",
            "get_turret",
            "get_grating_info",
            "get_turret_info",
            "set_filter",
            "get_filter",
            "home_filter",
        ],
    )
    parser.add_argument(
        "-p",
        "--parameter",
        help=(
            "parameter for function, i.e. wavelength in nm, grating number, turret "
            + "number, filter number"
        ),
    )
    args = parser.parse_args()

    # run command in context manager to ensure proper cleanup
    with sp2150() as mono:
        mono.connect(args.resource_name)

        # call function
        if args.function == "set_scan_speed":
            mono.scan_speed = args.parameter
        elif args.function == "get_scan_speed":
            print(mono.scan_speed)
        elif args.function == "scan_to_wavelength":
            mono.scan_to_wavelength(args.parameter)
        elif args.function == "goto_wavelength":
            mono.wavelength = args.parameter
        elif args.function == "get_wavelength":
            print(mono.wavelength)
        elif args.function == "set_grating":
            mono.grating = args.parameter
        elif args.function == "get_grating":
            print(mono.grating)
        elif args.function == "set_turret":
            mono.turret = args.parameter
        elif args.function == "get_turret":
            print(mono.turret)
        elif args.function == "get_grating_info":
            print(mono.grating_info)
        elif args.function == "get_turret_info":
            print(mono.turret_info)
        elif args.function == "set_filter":
            mono.filter = args.parameter
        elif args.function == "get_filter":
            print(mono.filter)
        elif args.function == "home_filter":
            mono.home_filter()
