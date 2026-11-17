"""Scope disclosure for the detergent ranking benchmark, not a price change."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from improve_purchase_pages import price_answer
from test_step4_purchase_audit import offer


class LaundryRankingScopeTests(unittest.TestCase):
    def test_laundry_ranking_minimum_discloses_separate_buying_choices(self):
        ranked = offer('laundry', 8.5, '100g', 89.26, 'rank',
                       title='さらさ 洗濯洗剤 詰め替え 850g')
        # A lower-priced STEP5 offer exists, but price_answer intentionally
        # calculates ranking statistics from items only.
        supplement = offer('laundry', 27.7, '100g', 75.81, 'value',
                           title='アタック 洗濯洗剤 詰め替え 2770g')
        data = {'metric': '100g', 'items': [ranked],
                'purpose_candidates': [supplement]}
        text = price_answer('laundry', data)
        self.assertIn('下の「今日の安い順ランキング」内の最低単価', text)
        self.assertIn('上部の「買う量から選ぶ」に表示される別候補は', text)
        self.assertIn('含めていません', text)
        self.assertIn('¥89.26', text)
        self.assertNotIn('¥75.81', text)
        self.assertIn('市場全体の最安値・相場ではありません', text)

    def test_empty_ranking_must_not_claim_scoped_minimum(self):
        text = price_answer('laundry', {'metric': '100g', 'items': []})
        self.assertIn('同じ条件で比較できる候補がありません', text)
        self.assertNotIn('下の「今日の安い順ランキング」内の最低単価', text)
        self.assertNotIn('上部の「買う量から選ぶ」に表示される別候補は', text)


if __name__ == '__main__':
    unittest.main()
