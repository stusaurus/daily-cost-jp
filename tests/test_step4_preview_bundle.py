import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from step4_prepare_candidate import refresh_diagnostic

class PreviewBundle(unittest.TestCase):
    current='<script id="step4-search-diagnostics">const api={explanation:true};</script>'

    def test_refreshes_existing_helper_and_preserves_price_url_and_other_scripts(self):
        protected='<a href="https://item.rakuten.co.jp/fixture/" data-shipping-price="1233">690g</a><script id="offer-validation">guard</script>'
        old='<head><script id="step4-search-diagnostics">stale</script></head>'+protected
        result=refresh_diagnostic(old,self.current)
        self.assertEqual(result,'<head>'+self.current+'</head>'+protected)
        self.assertNotIn('stale',result)

    def test_missing_helper_is_added_once_and_refresh_is_idempotent(self):
        result=refresh_diagnostic('<head></head>',self.current)
        self.assertEqual(refresh_diagnostic(result,self.current),result)
        self.assertEqual(result.count('id="step4-search-diagnostics"'),1)

    def test_duplicate_helpers_or_unknown_head_fail_closed(self):
        with self.assertRaises(ValueError):refresh_diagnostic('<head>'+self.current*2+'</head>',self.current)
        with self.assertRaises(ValueError):refresh_diagnostic('<main></main>',self.current)

if __name__=='__main__':unittest.main()
