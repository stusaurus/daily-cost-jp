"""Production and preview Lighthouse runs must not call live analytics."""
from pathlib import Path
import unittest

class LighthouseIsolationTests(unittest.TestCase):
    def test_all_existing_lighthouse_commands_block_collection_and_affiliate_redirect(self):
        count=0
        for path in Path('.github/workflows').glob('*.yml'):
            for line in path.read_text().splitlines():
                if 'npm exec' not in line or ' -- lighthouse ' not in line:continue
                count+=1
                with self.subTest(path=path,line=line):
                    self.assertIn('--blocked-url-patterns=',line)
                    self.assertIn('googletagmanager.com/',line)
                    self.assertIn('google-analytics.com/',line)
                    self.assertIn('hb.afl.rakuten.co.jp/',line)
        self.assertGreaterEqual(count,9)
