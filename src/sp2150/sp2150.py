"""Acton SP2150 monochromator control library."""

import pyvisa


class sp2150:
    """Monochromator instrument object."""

    def __init__(self):
        """Construct object."""
        self._write_termination = "\r"
        self._read_termination = " ok\r\n"
        self.instr = None

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

        # set instrument termchars
        self.instr.write_termination = self._write_termination
        self.instr.read_termination = self._read_termination

        # disable echo
        self.instr.query("NO-ECHO")

    def disconnect(self):
        """Disconnect instrument."""
        self.instr.close()

    def _query(self, cmd):
        """Query a command, stripping space at beginning of the response and the unit.

        When echo is disabled, the first character returned is a superfluous space,
        which can be removed.

        Some responses always contain a unit. This is also stripped so properties have
        values with the correct numeric type. The unit of a property can be found in
        its docstring.

        Parameters
        ----------
        cmd : str
            Command to query.

        Returns
        -------
        resp : str
            Response to command with receding space and unit stripped.
        """
        return self.instr.query(cmd)[1:].split(" ")[0]

    def _query_manual(self, cmd):
        """Query a command manually looking for the termination character.

        Some commands return partial termination characters, which pyvisa doesn't
        handle properly. This can be circumvented by reading characters one at a
        time and manually checking for the termination character.

        Parameters
        ----------
        cmd : str
            Command to query.

        Returns
        -------
        resp : str
            Response to command with receding space and unit stripped.
        """
        resp = b""
        self.instr.write(cmd)
        while resp.endswith(self._read_termination.encode("ASCII")) is False:
            resp += self.instr.read_bytes(1)

        return resp.decode("ASCII").strip(self._read_termination)

    @property
    def scan_speed(self):
        """Get grating scan speed in nm/min."""
        return float(self._query("?NM/MIN"))

    @scan_speed.setter
    def scan_speed(self, speed):
        """Set grating scan speed in nm/min."""
        self.instr.query(f"{float(speed):.1f} NM/MIN")

    def scan_to_wavelength(self, wavelength):
        """Scan grating to wavelength in nm."""
        # calculate scan time in ms
        scan_time = abs(wavelength - self.wavelength) * 60000 / self.scan_speed

        # if necessary, temporarily increase timeout for a wavelength scan
        old_timeout = self.instr.timeout
        if long_scan := scan_time > old_timeout:
            # add a few seconds buffer to scan timeout
            self.instr.timeout = scan_time + 5000

        # run the scan
        self.instr.query(f"{float(wavelength):.1f} NM")

        # reset timeout if needed
        if long_scan:
            self.instr.timeout = old_timeout

    @property
    def wavelength(self):
        """Get current grating wavelength position in nm."""
        return float(self._query("?NM"))

    @wavelength.setter
    def wavelength(self, wavelength):
        """Set grating position for wavelength in nm."""
        self.instr.query(f"{float(wavelength):.1f} GOTO")

    @property
    def grating(self):
        """Get grating number."""
        return int(self._query("?GRATING"))

    @grating.setter
    def grating(self, grating):
        """Set grating number."""
        self.instr.query(f"{int(grating)} GRATING")

    @property
    def turret(self):
        """Get turret number."""
        return int(self._query("?TURRET"))

    @turret.setter
    def turret(self, turret):
        """Set turrent number."""
        self.instr.query(f"{int(turret)} TURRET")

    @property
    def grating_info(self):
        """Get groove spacing and blaze wavelength of each grating."""
        return self._query_manual("?GRATINGS")

    # TODO: figure out why this command isn't recognised
    # @property
    # def turret_info(self):
    #     """Get groove spacing of each grating on each turret."""
    #     return self._query_manual("?TURRETS")

    @property
    def filter(self):
        """Get filter wheel position number."""
        return int(self._query("?FILTER"))

    @filter.setter
    def filter(self, filter_pos):
        """Set filter wheel position number."""
        self.instr.query(f"{int(filter_pos)} FILTER")

    def home_filter(self):
        """Set filter wheel to home position."""
        self.instr.query("FHOME")


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
        # elif args.function == "get_turret_info":
        #     print(mono.turret_info)
        elif args.function == "set_filter":
            mono.filter = args.parameter
        elif args.function == "get_filter":
            print(mono.filter)
        elif args.function == "home_filter":
            mono.home_filter()
