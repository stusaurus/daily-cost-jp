import sys
import unittest
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
from candidate_acquisition import acquire, identity, SUPPLEMENTAL_QUERIES
from product_quality import filter_items, REQUIRED


def offer(index, title=None):
    return dict(item_code=f'shop:{index}', name=title or f'抗菌 紙軸 綿棒100本 商品{index}',
                shop='shop', price=1000+index, unit_price=(1000+index)/100,
                confidence=.99, metric='piece', postage='送料込み',
                url=f'https://item.rakuten.co.jp/shop/{index}/')


def rank(items):
    return 'piece', sorted(items, key=lambda p:p['unit_price'])[:5]


class CandidateAcquisitionTests(unittest.TestCase):
    category = {'id':'cotton-swab', 'keyword':'綿棒'}

    def test_all_categories_have_bounded_concrete_queries(self):
        self.assertEqual(set(SUPPLEMENTAL_QUERIES), set(REQUIRED))
        self.assertTrue(all(1 <= len(q) <= 3 for q in SUPPLEMENTAL_QUERIES.values()))

    def test_no_extra_requests_when_first_page_is_sufficient(self):
        fetch = Mock(return_value=[offer(n) for n in range(5)])
        rows, report = acquire(self.category,fetch,lambda x,c:x,rank,Mock())
        self.assertEqual(fetch.call_count,1)
        self.assertEqual(report['baseline']['ranked'],5)
        self.assertEqual(len(rows),5)

    def test_expansion_still_rejects_wrong_use_and_deduplicates(self):
        bad=offer(99,'IQOS用 綿棒100本')
        fetch=Mock(side_effect=[[offer(0),bad],[offer(0),bad],
                               [bad,*[offer(n) for n in range(1,6)]]])
        rows,report=acquire(self.category,fetch,lambda x,c:x,rank,Mock())
        self.assertEqual(report['baseline']['ranked'],1)
        self.assertEqual(report['ranked'],5)
        self.assertEqual(report['duplicates_removed'],3)
        self.assertEqual(len(filter_items('cotton-swab',rows)),6)
        self.assertEqual(report['requests'][-1]['query'],'紙軸 綿棒 200本')
        self.assertTrue(fetch.call_args.args[0]['_supplementary'])

    def test_optional_errors_keep_safe_first_page_and_bound_cost(self):
        fetch=Mock(side_effect=[[offer(0)],TimeoutError(),TimeoutError(),[],[]])
        pause=Mock()
        rows,report=acquire(self.category,fetch,lambda x,c:x,rank,pause)
        self.assertEqual(rows,[offer(0)])
        self.assertEqual(fetch.call_count,5)
        self.assertEqual(pause.call_count,4)
        self.assertEqual(report['requests'][1]['error'],'TimeoutError')

    def test_first_page_failure_remains_a_failure(self):
        with self.assertRaises(TimeoutError):
            acquire(self.category,Mock(side_effect=TimeoutError()),lambda x,c:x,rank,Mock())

    def test_affiliate_tracking_differences_do_not_duplicate_one_offer(self):
        one={'url':'https://hb.afl.rakuten.co.jp/hgc/a/?pc=https%3A%2F%2Fitem.rakuten.co.jp%2Fs%2Fi%2F&rafcid=first'}
        two={'url':'https://item.rakuten.co.jp/s/i/?scid=second'}
        self.assertEqual(identity(one),identity(two))
