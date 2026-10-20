"""Regression for a public API title; no live requests or inferred brand specs."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from product_quality import COUNT_UNITS,category_rejection,safer_parse_count_quantity,explicit_tissue_box_total

TITLE='エリエール ティシュー 360枚(180組)×5個パック×3セット 合計15箱 （沖縄・離島は配送不可） お得なティッシュ'


class TissueExplicitTotalTests(unittest.TestCase):
    def test_observed_total_is_corroborated_by_pack_arithmetic(self):
        parsed=safer_parse_count_quantity(TITLE,COUNT_UNITS['tissue'])
        self.assertEqual(parsed['quantity'],15)
        self.assertEqual(parsed['metric'],'box')
        self.assertEqual(parsed['confidence'],0.99)
        self.assertIsNone(category_rejection('tissue',TITLE))

    def test_ambiguous_contradictory_or_extra_counts_are_not_accepted(self):
        for title in (TITLE.replace('合計15箱','合計14箱'),TITLE+' 10箱',
                      TITLE+' 選べる数量',TITLE.replace('3セット','0セット'),
                      TITLE.replace('合計15箱','合計15箱／20箱')):
            with self.subTest(title=title):
                self.assertIsNone(safer_parse_count_quantity(title,COUNT_UNITS['tissue']))

    def test_missing_stated_total_is_not_promoted_from_packs_to_boxes(self):
        title=TITLE.replace('合計15箱','')
        parsed=safer_parse_count_quantity(title,COUNT_UNITS['tissue'])
        self.assertTrue(parsed is None or parsed['metric']!='box')
        self.assertIsNotNone(category_rejection('tissue',title))

    def test_type_is_not_inferred_from_brand_and_non_tissue_stays_rejected(self):
        for title in (TITLE.replace('ティシュー','商品').replace('ティッシュ','商品'),
                      TITLE.replace('180組','180単位'), 'ウェット '+TITLE, 'ポリ袋 '+TITLE):
            with self.subTest(title=title):
                self.assertIsNotNone(category_rejection('tissue',title))

    def test_other_count_categories_do_not_use_the_tissue_total(self):
        self.assertIsNone(safer_parse_count_quantity(TITLE,COUNT_UNITS['toothbrush']))

    def test_decimal_or_following_multiplier_does_not_use_explicit_total_shortcut(self):
        for title in (TITLE.replace('5個','3.5個'),TITLE.replace('合計15箱','合計15箱×2'),TITLE+' 1.5箱'):
            with self.subTest(title=title):
                self.assertIsNone(explicit_tissue_box_total(title))
                self.assertIsNotNone(category_rejection('tissue',title))


if __name__=='__main__':unittest.main()
