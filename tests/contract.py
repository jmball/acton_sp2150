"""Public behavior shared by simulator, fake-backed driver, and real hardware."""


class InstrumentContract:
    """Mix into a TestCase that supplies a connected device and test targets."""

    wavelength_target = 500.0
    scan_target = 501.0
    scan_speed_target = 600.0
    grating_target = 2
    turret_target = 1
    filter_target = 3
    home_filter_position = 1
    wavelength_tolerance = 0.11

    def test_scan_speed(self):
        self.device.scan_speed = str(self.scan_speed_target)
        self.assertIsInstance(self.device.scan_speed, float)
        self.assertAlmostEqual(self.device.scan_speed, self.scan_speed_target, delta=0.11)

    def test_direct_wavelength(self):
        self.device.wavelength = str(self.wavelength_target)
        self.assertIsInstance(self.device.wavelength, float)
        self.assertAlmostEqual(
            self.device.wavelength, self.wavelength_target, delta=self.wavelength_tolerance
        )

    def test_scanned_wavelength(self):
        self.device.wavelength = self.wavelength_target
        self.device.scan_speed = self.scan_speed_target
        self.device.scan_to_wavelength(str(self.scan_target))
        self.assertAlmostEqual(
            self.device.wavelength, self.scan_target, delta=self.wavelength_tolerance
        )

    def test_grating(self):
        self.device.turret = self.turret_target
        self.device.grating = str(self.grating_target)
        self.assertIsInstance(self.device.grating, int)
        self.assertEqual(self.device.grating, self.grating_target)

    def test_turret(self):
        self.device.turret = str(self.turret_target)
        self.assertIsInstance(self.device.turret, int)
        self.assertEqual(self.device.turret, self.turret_target)

    def test_filter(self):
        self.device.filter = str(self.filter_target)
        self.assertIsInstance(self.device.filter, int)
        self.assertEqual(self.device.filter, self.filter_target)

    def test_home_filter(self):
        self.device.filter = self.filter_target
        self.device.home_filter()
        self.assertEqual(self.device.filter, self.home_filter_position)

    def test_grating_information(self):
        self.assertIsInstance(self.device.grating_info, str)
        self.assertTrue(self.device.grating_info.strip())

    def test_turret_information(self):
        self.assertIsInstance(self.device.turret_info, str)
        self.assertTrue(self.device.turret_info.strip())
