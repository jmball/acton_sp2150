"""Acton SP2150 monochromator control library."""

import pyvisa


class sp2150:
    """Monochromator instrument object."""

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
        resource_manager : pyvisa.ResourceManager, optional
            Resource manager used to create new connection. If `None`, create a new
            resource manager using system set VISA backend.
        resource_kwargs : dict
            Keyword arguments passed to PyVISA resource to be used to change
            instrument attributes after construction.
        """
        if resource_manager is None:
            resource_manager = pyvisa.ResourceManager()
        self.instr = resource_manager.open_resource(resource_name, **resource_kwargs)

    def disconnect(self):
        """Disconnect instrument."""
        self.instr.close()

    def _setter_query(self, cmd):
        """Send a command to set a value and validate output.

        Paramters
        ---------
        cmd : str
            Command to issue.
        """
        resp = self.instr.query(cmd)

        # check cmd was successful
        if not resp.endswith("ok\r\n"):
            raise ValueError(
                f"Command failed. Check parameter and try again. Instrument response "
                + f"message: {resp}"
            )

    @property
    def scan_speed(self):
        """Get grating scan speed in nm/min."""
        return float(self.instr.query("?NM/MIN").strip(" ok\r\n"))

    @scan_speed.setter
    def scan_speed(self, speed):
        """Set grating scan speed in nm/min."""
        self._setter_query(f"{float(speed):.1f} NM/MIN")

    def scan_to_wavelength(self, wavelength):
        """Scan grating to wavelength in nm."""
        resp = self.instr.query(f"{float(wavelength):.1f} NM")

        # check cmd was successful
        if not resp.endswith("ok\r\n"):
            raise ValueError(
                f"Command failed. Check parameter and try again. Instrument response "
                + f"message: {resp}"
            )

    @property
    def wavelength(self):
        """Get current grating wavelength position in nm."""
        return float(self.instr.query("?NM").strip(" ok\r\n"))

    @wavelength.setter
    def wavelength(self, wavelength):
        """Set grating position for wavelength in nm."""
        self._setter_query(f"{float(wavelength):.1f} GOTO")

    @property
    def grating(self):
        """Get grating number."""
        return int(self.instr.query("?GRATING").strip(" ok\r\n"))

    @grating.setter
    def grating(self, grating):
        """Set grating number."""
        self._setter_query(f"{int(grating)} GRATING")

    @property
    def turret(self):
        """Get turret number."""
        return int(self.instr.query("?TURRET").strip(" ok\r\n"))

    @turret.setter
    def turret(self, turret):
        """Set turrent number."""
        self._setter_query(f"{int(turret)} TURRET")

    @property
    def grating_info(self):
        """Get groove spacing and blaze wavelength of each grating."""
        return self.instr.query("?GRATINGS").strip(" ok\r\n")

    @property
    def turret_info(self):
        """Get groove spacing of each grating on each turret."""
        return self.instr.query("?TURRETS").strip(" ok\r\n")

    @property
    def filter(self):
        """Get filter wheel position number."""
        return int(self.instr.query("?FILTER").strip(" ok\r\n"))

    @filter.setter
    def filter(self, filter_pos):
        """Set filter wheel position number."""
        self._setter_query(f"{int(filter_pos)} FILTER")

    def home_filter(self):
        """Set filter wheel to home position."""
        self.instr.query("FHOME").strip(" ok\r\n")


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
