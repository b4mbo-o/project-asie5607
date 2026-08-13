import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class SupervisorTests(unittest.TestCase):
    def test_failed_worker_is_restarted_without_reset_command(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            count = root / "count"
            harness = root / "harness.py"
            harness.write_text(textwrap.dedent(f"""\
                import os
                import sys
                sys.path.insert(0, {str(ROOT / 'scripts')!r})
                from daemon_supervisor import supervise, worker_process
                from pathlib import Path

                if worker_process():
                    counter = Path({str(count)!r})
                    value = int(counter.read_text()) + 1 if counter.exists() else 1
                    counter.write_text(str(value))
                    raise SystemExit(2 if value == 1 else 0)
                raise SystemExit(supervise(Path(__file__), 'test-daemon'))
            """))
            result = subprocess.run(
                [sys.executable, str(harness), "--retry-seconds", "0.1", "--max-restarts", "1"],
                text=True, capture_output=True, timeout=5,
            )
            self.assertEqual(count.read_text(), "2")
            self.assertIn("restarting without USB reset", result.stderr)
            self.assertNotIn("libusb_reset", result.stderr)


if __name__ == "__main__":
    unittest.main()
