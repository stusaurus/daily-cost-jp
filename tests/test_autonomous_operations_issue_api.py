import io
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import autonomous_operations_issue as issue


class GitHubAPIResponseTests(unittest.TestCase):
    def test_large_pr_page_is_read_completely(self):
        # Real 100-PR pages can be >1 MB; the previous 250 KB read truncated JSON.
        prs = [{"number": i, "body": "x" * 14000} for i in range(100)]
        raw = json.dumps(prs).encode("utf-8")
        self.assertGreater(len(raw), 250_000)
        self.assertLess(len(raw), issue.MAX_RESPONSE_BYTES)
        with patch.object(issue, "urlopen", return_value=io.BytesIO(raw)):
            result = issue.github_request("/pulls?state=all&per_page=100&page=1", "test-token")
        self.assertEqual(len(result), 100)
        self.assertEqual(result[-1]["number"], 99)
        self.assertEqual(result[-1]["body"], "x" * 14000)

    def test_oversized_response_fails_closed(self):
        # Allow enough room for the full page, but never buffer indefinitely.
        raw = b" " * (issue.MAX_RESPONSE_BYTES + 1)
        with patch.object(issue, "urlopen", return_value=io.BytesIO(raw)):
            with self.assertRaisesRegex(ValueError, "safe size limit"):
                issue.github_request("/pulls?state=all&per_page=100&page=1", "test-token")

    def test_malformed_response_is_not_treated_as_empty_listing(self):
        with patch.object(issue, "urlopen", return_value=io.BytesIO(b'[{"body":"unfinished')):
            with self.assertRaises(json.JSONDecodeError):
                issue.github_request("/pulls?state=all&per_page=100&page=1", "test-token")

    def test_api_errors_are_not_silenced(self):
        error = HTTPError("https://api.github.com", 403, "forbidden", {}, None)
        with patch.object(issue, "urlopen", side_effect=error):
            with self.assertRaises(HTTPError) as raised:
                issue.github_request("/pulls?state=all&per_page=100&page=1", "test-token")
        self.assertEqual(raised.exception.code, 403)


if __name__ == "__main__":
    unittest.main()
