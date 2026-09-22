import sys
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
from promote_home_ranking import extract_rows, item_link


class RankingLinkTests(unittest.TestCase):
    def test_affiliate_parameters_survive_html_roundtrip(self):
        markup = '''<article class="card"><div class="pic"><img src="https://example.test/a?a=1&amp;b=2"></div><div><div class="rank"><b>1位</b></div><div class="name">商品</div><div class="meta">価格</div><div class="actions"><a class="rakuten" href="https://hb.afl.rakuten.co.jp/hgc/test/?pc=https%3A%2F%2Fitem.rakuten.co.jp%2Fshop%2Fsku%2F&amp;rafcid=test">楽天</a></div></div></article>'''
        row = extract_rows(markup)[0]
        query = parse_qs(urlsplit(item_link(row)).query)
        self.assertEqual(query['rafcid'], ['test'])
        self.assertNotIn('amp;rafcid', query)
        self.assertEqual(query['pc'], ['https://item.rakuten.co.jp/shop/sku/'])
