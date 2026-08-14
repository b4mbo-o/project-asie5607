import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "probe_u3_satellite", ROOT / "scripts" / "probe_u3_satellite.py"
)
probe = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(probe)


class SatelliteProbeTests(unittest.TestCase):
    def test_channel_table_contains_all_supported_physical_transponders(self):
        self.assertEqual(len(probe.CHANNELS), 24)
        self.assertEqual(probe.CHANNELS[:12], tuple(f"BS{number:02d}_0" for number in range(1, 24, 2)))
        self.assertEqual(probe.CHANNELS[12:], tuple(f"CS{number}" for number in range(2, 25, 2)))

    def test_mirakurun_entry_names(self):
        self.assertEqual(probe.mirakurun_item("BS13_0"), ("BS", "U3-BS13"))
        self.assertEqual(probe.mirakurun_item("CS22"), ("CS", "U3-CS22"))


if __name__ == "__main__":
    unittest.main()
