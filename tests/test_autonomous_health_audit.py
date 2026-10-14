"""Offline unit tests for the autonomous health audit."""
import importlib.util
import pathlib
import unittest
from unittest.mock import patch
from io import BytesIO

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "autonomous_health_audit.py"
spec = importlib.util.spec_from_file_location("autonomous_health_audit", SCRIPT)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)

class FakeResponse:
    status = 200
    def __enter__(self):
        return self
    def __exit__(self, *_):
        return False
    def read(self, n):
        return b"<html>ok</html>"

class HealthAuditTests(unittest.TestCase):
    @patch.object(audit, "urlopen", return_value=FakeResponse())
    def test_healthy_endpoint(self, mocked):
        result = audit.check("/")
        self.assertEqual(result["status"], "pass")
        self.assertEqual(mocked.call_count, 1)

    @patch.object(audit.time, "sleep")
    @patch.object(audit, "urlopen", side_effect=TimeoutError("offline"))
    def test_failure_is_bounded(self, mocked, sleep):
        result = audit.check("/categories/laundry/")
        self.assertEqual(result["status"], "fail")
        self.assertEqual(mocked.call_count, 3)
        self.assertEqual(sleep.call_count, 2)

    @patch.object(audit.time, "sleep")
    @patch.object(audit, "urlopen", side_effect=[TimeoutError("temporary"), FakeResponse()])
    def test_transient_failure_recovers(self, mocked, sleep):
        result = audit.check("/categories/tissue/")
        self.assertEqual(result["status"], "pass")
        self.assertEqual(mocked.call_count, 2)

if __name__ == "__main__":
    unittest.main()
