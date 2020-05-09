"""Acton SP2150 monochromator control library."""

import visa

rm = visa.ResourceManager()


class sp2150:
    """Monochromator instrument object."""

    def __init__(self):
        """Instantiate PyVISA instrument object.

        Default termination char settings for PyVISA are compatible with RS232.
        """

    def connect(self, resource_name, timeout=10000):
        """Connect to instrument.
        
        Parameters
        ----------
        address : str
            Full VISA resource address, e.g. "ASRL2::INSTR", "GPIB0::14::INSTR" etc.
        timeout: int or float, optional
            Communication timeout in ms.
        """
        self.instr = rm.open_resource(resource_name)
        self.instr.timeout = self.timeout

    def disconnect(self):
        """Disconnect instrument."""
        self.instr.close()

    def set_scan_speed(self, speed):
        """Set grating scan speed in nm/min."""
        return self.instr.query(f"{float(speed):.1f} NM/MIN")

    def get_scan_speed(self):
        """Get grating scan speed in nm/min."""
        return self.instr.query("?NM/MIN")

    def scan_to_wavelength(self, wavelength):
        """Scan grating to wavelength in nm."""
        return self.instr.query(f"{float(wavelength):.1f} NM")

    def goto_wavelength(self, wavelength):
        """Go to grating position for wavelength in nm."""
        return self.instr.query(f"{float(wavelength):.1f} GOTO")

    def get_wavelength(self):
        """Get current grating wavelength position in nm."""
        return self.instr.query("?NM")

    def set_grating(self, grating):
        """Set grating number."""
        return self.instr.query(f"{int(grating)} GRATING")

    def get_grating(self):
        """Get grating number."""
        return self.instr.query("?GRATING")

    def set_turret(self, turret):
        """Set turrent number."""
        return self.instr.query(f"{int(turret)} TURRET")

    def get_turret(self):
        """Get turret number."""
        return self.instr.query("?TURRET")

    def get_grating_info(self):
        """Get groove spacing and blaze wavelength of each grating."""
        return self.instr.query("?GRATINGS")

    def get_turret_info(self):
        """Get groove spacing of each grating on each turret."""
        return self.instr.query("?TURRETS")

    def set_filter(self, filter_pos):
        """Set filter wheel position number."""
        return self.instr.query(f"{int(filter_pos)} FILTER")

    def get_filter(self):
        """Get filter wheel position number."""
        return self.instr.query("?FILTER")

    def home_filter(self):
        """Set filter wheel to home position."""
        return self.instr.query("FHOME")


if __name__ == "__main__":

    import argparse

    # set up cli
    parser = argparse.ArgumentParser()
    parser.add_argument("address", help="instrument address")
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
        help="parameter for function, i.e. wavelength in nm, grating number, turret number, filter number",
    )
    args = parser.parse_args()

    # create instrument instance
    mono = sp2150(args.address)

    # call function
    if args.function == "set_scan_speed":
        resp = mono.set_scan_speed(args.parameter)
    elif args.function == "get_scan_speed":
        resp = mono.get_scan_speed()
    elif args.function == "scan_to_wavelength":
        resp = mono.scan_to_wavelength(args.parameter)
    elif args.function == "goto_wavelength":
        resp = mono.goto_wavelength(args.parameter)
    elif args.function == "get_wavelength":
        resp = mono.get_wavelength()
    elif args.function == "set_grating":
        resp = mono.set_grating(args.parameter)
    elif args.function == "get_grating":
        resp = mono.get_grating()
    elif args.function == "set_turret":
        resp = mono.set_turret(args.parameter)
    elif args.function == "get_turret":
        resp = mono.get_turret()
    elif args.function == "get_grating_info":
        resp = mono.get_grating_info()
    elif args.function == "get_turret_info":
        resp = mono.get_turret_info()
    elif args.function == "set_filter":
        resp = mono.set_filter(args.parameter)
    elif args.function == "get_filter":
        resp = mono.get_filter()
    elif args.function == "home_filter":
        resp = mono.home_filter()

    # check cmd was successful
    if not resp.endswith("ok\r\n"):
        raise ValueError(
            f"Command failed. Check parameter and try again. Instrument response msg: {resp}"
        )

    print(resp.strip(" ok\r\n"))
