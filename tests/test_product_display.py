from copy import deepcopy
from datetime import datetime
from pathlib import Path
import sys
import unittest
from zoneinfo import ZoneInfo

sys.path.insert(0,str(Path(__file__).parents[1]/'scripts'))
from product_display import clean_display_name
from build_daily_deals import render_page


class ProductDisplayTests(unittest.TestCase):
    def test_expired_promotion_prefix_removed(self):
        product='ペーパータオル エコタイプ 小判 200枚入 × 40袋'
        for prefix in ['【9/25 24時間限定★P5倍＋最大1,500円OFFクーポン】',
                       '【9月25日限定】【ポイント10倍】', '＼マラソン中／【P10倍】',
                       '【P最大13倍★9/25限定】', '＼P5倍☆彡〜28日9:59迄／',
                       '【セール中 9/28 23:59迄】',
                       '【最大1000円引クーポン9/29 9:59迄】',
                       '【最大1,500円引きクーポン】【ポイント最大10倍】',
                       '【9/30限定☆先着クーポンで69円！】＼ランキング1位／高評価 ',
                       '高評価＼★2022年間ランキング1位受賞!／【先着限定クーポンで最安1箱152円】9/29 23:59迄 ',
                       'レビュー記入で300円クーポンプレゼント♪ ',
                       '【楽天1位】【まとめ買いお得】',
                       '【365日最短当日出荷！】',
                       '【10/1限定＼当選確率2分の1／最大100%ポイントバック】',
                       '【 10月1日から31日限定！ エントリーで全品ポイント5倍】ランキング1位受賞 ',
                       '【まとめ買いお得！★クーポン利用で498円~】【高評価人気商品】',
                       '本日限定！ ']:
            self.assertEqual(clean_display_name(prefix+product),product)

    def test_product_identity_labels_are_never_removed(self):
        for title in ['【アタックZERO】ドラム式専用 本体400g',
                      '【6個セット】アタックZERO 詰め替え2100g',
                      '【無添加 泡ハンドソープ 詰め替え】230ml×3個',
                      '【9/25限定 アタックZERO 2100g】詰め替え',
                      '【P5倍 200枚×40袋】ペーパータオル',
                      '【1000円引クーポン アタックZERO】詰替2100g',
                      '【エリエール】ティッシュ200組5箱',
                      '【ポイント10倍】']:
            self.assertEqual(clean_display_name(title),title)

    def test_promo_then_product_label_keeps_product_label(self):
        self.assertEqual(clean_display_name('【P5倍】【6個セット】アタックZERO 詰め替え2100g'),
                         '【6個セット】アタックZERO 詰め替え2100g')

    def test_today_display_changes_without_mutating_source_or_url(self):
        row=dict(id='paper-towel',name='ペーパータオル',emoji='🧻',
                 product_name='【9/25 24時間限定★P5倍＋最大1,500円OFFクーポン】ペーパータオル200枚×40袋',
                 url='https://hb.afl.rakuten.co.jp/hgc/test/?pc=product&rafcid=keep',
                 image='https://example.org/product.jpg',price=3978,unit_price=.49725,
                 metric='sheet',metric_label='1枚',discount=23,shop='shop',median=.65,sample=5,
                 sale_quantity_label='200枚×40袋')
        original=deepcopy(row)
        markup=render_page([row],datetime(2026,9,26,tzinfo=ZoneInfo('Asia/Tokyo')))
        self.assertNotIn('9/25',markup)
        self.assertIn('<h2>ペーパータオル200枚×40袋</h2>',markup)
        self.assertIn('rafcid=keep',markup)
        self.assertIn('3,978',markup)
        self.assertEqual(row,original)
        self.assertEqual(clean_display_name(clean_display_name(row['product_name'])),clean_display_name(row['product_name']))
