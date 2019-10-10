# created by James Ball, 2019-10-10

import visa

class ActonSP2150():

    def __init__(self, addr, timeout=10000):
        """Default termination char settings for PyVISA are compatible with RS232"""
        rm = visa.ResourceManager()
        self.instr = rm.open_resource(addr)
        self.instr.timeout = timeout

    
    def set_scan_speed(self, speed):
        """Set grating scan speed in nm/min"""
        return self.instr.query(f'{float(speed):.1f} NM/MIN')
    

    def get_scan_speed(self):
        """Get grating scan speed in nm/min"""
        return self.instr.query('?NM/MIN')
    

    def scan_to_wavelength(self, wavelength):
        """Scan grating to wavelength in nm"""
        return self.instr.query(f'{float(wavelength):.1f} NM')


    def goto_wavelength(self, wavelength):
        """Go to grating position for wavelength in nm"""
        return self.instr.query(f'{float(wavelength):.1f} GOTO')
    
    def get_wavelength(self):
        """Get current grating wavelength position in nm"""
        return self.instr.query('?NM')
    

    def set_grating(self, grating):
        """Set grating number"""
        return self.instr.query(f'{int(grating)} GRATING')

    
    def get_grating(self):
        """Get grating number"""
        return self.instr.query('?GRATING')

    
    def set_turret(self, turret):
        """Set turrent number"""
        return self.instr.query(f'{int(turret)} TURRET')

    
    def get_turret(self):
        """Get turret number"""
        return self.instr.query('?TURRET')

    
    def get_grating_info(self):
        """Get groove spacing and blaze wavelength of each grating"""
        return self.instr.query('?GRATINGS')

    
    def get_turret_info(self):
        """Get groove spacing of each grating on each turret"""
        return self.instr.query('?TURRETS')
    

    def set_filter(self, filter_pos):
        """Set filter wheel position number"""
        return self.instr.query(f'{int(filter_pos)} FILTER')

    
    def get_filter(self):
        """Get filter wheel position number"""
        return self.instr.query('?FILTER')


    def home_filter(self):
            """Set filter wheel to home position"""
            return self.instr.query('FHOME')