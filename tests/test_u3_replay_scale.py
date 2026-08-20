import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts" / "run_u3_full_secure_terrestrial.py"
DAEMON = ROOT / "scripts" / "u3d"


class ReplayScaleOptionTests(unittest.TestCase):
    def test_invalid_scale_is_rejected_before_usb_access(self):
        result = subprocess.run(
            [sys.executable, str(RUNNER), "--port", "5", "--replay-scale", "0"],
            text=True, capture_output=True,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("replay-scale must be in (0, 1]", result.stderr)

    def test_daemon_reports_scale_in_dry_run(self):
        result = subprocess.run(
            [sys.executable, str(DAEMON), "--dry-run", "--bus", "2", "--port", "5",
             "--replay-scale", "0.5"],
            text=True, capture_output=True, check=True,
        )
        self.assertIn("replay_scale=0.5", result.stdout)

    def test_invalid_early_scale_is_rejected_before_usb_access(self):
        result = subprocess.run(
            [sys.executable, str(RUNNER), "--port", "5", "--early-replay-scale", "1.1"],
            text=True, capture_output=True,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("early-replay-scale must be in (0, 1]", result.stderr)

    def test_terrestrial_selector_is_rejected_for_satellite_bootstrap(self):
        result = subprocess.run(
            [sys.executable, str(RUNNER), "--port", "5", "--satellite-channel", "21"],
            text=True, capture_output=True,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("satellite-channel must be a BS or CS selector", result.stderr)


if __name__ == "__main__":
    unittest.main()
