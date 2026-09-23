from copy import deepcopy
from datetime import datetime
import json
import sys
import tempfile
import unittest
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
import product_quality as quality
import build_daily_deals as deals
import validate_product_quality as gate
import sync_trend_search_chips as chips
import promote_home_ranking as ranking

# Normal consumables AND a plausible false positive for each of 21 categories.
CASES = {
 'toilet-paper': ('トイレットペーパー シングル 12ロール', 'トイレットペーパー ホルダー 2個'),
 'tissue': ('ボックスティッシュ 200組5箱', 'ティッシュケース ボックスティッシュ用 5箱'),
 'laundry': ('さらさ 洗濯洗剤1490g', 'アリエール 洗濯槽クリーナー500g'),
 'dish': ('キュキュット 食器用洗剤700ml', '食器用洗剤用 ディスペンサー700ml'),
 'water': ('天然水 2L×6本', '天然水 ウォーターサーバー2L'),
 'coffee': ('コーヒー豆500g', 'コーヒー豆保存キャニスター 空容器500g'),
 'softener': ('さらさ 柔軟剤1350ml', '洗濯用石けん 柔軟剤不要 5L'),
 'shampoo': ('シャンプー1000ml', '犬用シャンプー1000ml'),
 'conditioner': ('コンディショナー1800ml', 'シャンプーボトル コンディショナー600ml×3本'),
 'body-soap': ('ボディソープ1000ml', 'トリートメント1000ml ボディソープシリーズ'),
 'hand-soap': ('ハンドソープ450ml', 'ハンドソープ用 空ボトル450ml'),
 'bath-cleaner': ('お風呂用洗剤800ml', 'お風呂用洗剤ブラシ 2本'),
 'toilet-cleaner': ('トイレ用洗剤190ml', 'トイレ用洗剤 撥水コーティング剤1L'),
 'laundry-bleach': ('ワイドハイターEX 衣料用漂白剤4.5L', 'キッチン用 衣料用漂白剤ボトル1L'),
 'mouthwash': ('マウスウォッシュ500ml', 'マウスウォッシュ携帯容器500ml'),
 'paper-towel': ('ペーパータオル200枚×30袋', 'ペーパータオル ホルダー2個'),
 'garbage-bag-45l': ('ゴミ袋45L 100枚', 'ゴミ袋45L用ゴミ箱 1個'),
 'mask': ('不織布マスク51枚', '不織布マスクケース51枚用'),
 'toothbrush': ('歯ブラシ6本', '電動歯ブラシ 替えブラシ6本'),
 'cotton-swab': ('抗菌 紙軸 綿棒200本', 'IQOS glo 電子タバコ用 綿棒100本'),
 'floor-sheet': ('フローリング ウェットシート20枚', 'フローリング シート床材20枚'),
}


def item(title='衛生用 綿棒100本', price=1000):
    return dict(name=title, price=price, unit_price=price/100, confidence=.99,
                metric='piece', postage='送料込み', url='https://hb.afl.rakuten.co.jp/hgc/test/')


class ProductQualityTests(unittest.TestCase):
    def test_real_public_products_snapshot(self):
        rows = json.loads((Path(__file__).parent / 'fixtures/public_products_20260923.json').read_text())
        self.assertEqual(len(rows), 75)
        for row in rows:
            with self.subTest(category=row['category'], title=row['item']['name']):
                self.assertEqual(quality.item_rejection(row['category'],row['item']) is None, row['approved'])

    def test_unknown_category_fails_closed(self):
        self.assertFalse(quality.category_is_suitable('not-configured', '衛生用 綿棒100本'))

    def test_no_false_negative_for_safe_bulk_cases_and_negative_claims(self):
        for cid,title in [('softener','柔軟剤1350ml×6袋 1ケース'),
                          ('laundry','洗濯洗剤 無漂白剤 1.3kg×4袋（詰替容器スプーンなし）'),
                          ('laundry','洗濯洗剤 柔軟剤不要 1L'),
                          ('mask','不織布マスク51枚')]:
            self.assertTrue(quality.category_is_suitable(cid,title),title)

    def test_all_electronic_tobacco_and_ear_tools_are_excluded(self):
        for title in ['glo 綿棒100本','アイコス用綿棒30本','Ploom 綿棒30本','精密機器用 綿棒100本',
                      '粘着式耳かき 綿棒24本','再利用 合成ゴム 綿棒24本']:
            self.assertFalse(quality.category_is_suitable('cotton-swab',title))

    def test_hygiene_evidence_required_even_when_title_says_cotton_swab(self):
        for title in ['綿棒100本', '加湿器 フィルター 交換用6本 綿棒 給水芯',
                      '加湿フィルター8×200mm 棒状交換用6本 綿棒',
                      '5本セット 綿棒 給水芯 コットンバー 吸水芯',
                      '犬 猫 歯磨き オーラバイオブラシ 綿棒サイズ 歯ブラシ2本セット',
                      '紙軸 綿棒100本 精密機器クリーニング用',
                      '抗菌 綿棒6本 加湿器交換用フィルター']:
            self.assertFalse(quality.category_is_suitable('cotton-swab',title),title)
        for title in ['紙軸 綿棒200本','衛生用 綿棒100本','ベビー綿棒100本','メイク用 綿棒200本']:
            self.assertTrue(quality.category_is_suitable('cotton-swab',title),title)

    def test_device_parts_are_rejected_in_every_category(self):
        for cid, (good, _) in CASES.items():
            self.assertFalse(quality.category_is_suitable(cid,good+' 交換用フィルター 給水芯'),cid)

    def test_wrong_use_prices_do_not_turn_hygiene_swabs_into_outliers(self):
        good=item(price=100)
        wrong=[]
        for title in ['加湿器 綿棒 6本 給水芯','交換用フィルター 綿棒6本','ペット用 歯ブラシ 綿棒サイズ6本']:
            row=item(title,price=458);row['unit_price']=458/6
            wrong.append(row)
        safe=quality.filter_items('cotton-swab',[good,*wrong])
        self.assertEqual([p['name'] for p in safe],[good['name']])

    def test_selectable_counts_and_capacities(self):
        for title in ['不織布マスク100 80 50 20枚','洗濯洗剤500ml/1000ml',
                      '洗濯洗剤 容量選択 1000ml','綿棒100本 個数を選べる']:
            self.assertTrue(quality.ambiguous_quantity(title),title)
        self.assertIsNone(quality.parsed_quantity('mask','不織布マスク20枚×1袋 大容量51枚'))

    def test_repeat_total_is_not_a_quantity_variant(self):
        self.assertEqual(quality.parsed_quantity('tissue','ボックスティッシュ5箱×12パック(60箱)')['quantity'],60)
        self.assertEqual(quality.parsed_quantity('paper-towel','ペーパータオル200枚×40袋8000枚')['quantity'],8000)

    def test_bad_unit_price_cannot_pass_with_forged_quality_flag(self):
        bad=item();bad.update(unit_price=1,quality_version=quality.VERSION)
        self.assertEqual(quality.item_rejection('cotton-swab',bad),'quantity_price_mismatch')
        bad=item();bad['metric']='100ml'
        self.assertEqual(quality.item_rejection('cotton-swab',bad),'unit_mismatch')
        bad=item();bad['price']=float('nan')
        self.assertIsNotNone(quality.item_rejection('cotton-swab',bad))

    def test_extreme_isolated_outlier_is_removed_upstream(self):
        rows=[item(price=p) for p in [1,1000,1100,1200,1300]]
        self.assertEqual(len(quality.filter_items('cotton-swab',rows)),4)

    def test_today_filters_legacy_or_injected_bad_products(self):
        rows=[item(price=p) for p in [800,1000,1100,1200,1300]]
        rows.append(item('IQOS 電子タバコ用 綿棒100本',100))
        result=deals.choose_category('cotton-swab',{'items':rows,'name':'綿棒'},min_discount=1)
        self.assertIsNotNone(result)
        self.assertEqual(result['product_name'],'衛生用 綿棒100本')
        self.assertEqual(result['sample'],5)
        # Five bad offers must never supply the minimum sample for a deal.
        self.assertIsNone(deals.choose_category('cotton-swab',{'items':[rows[-1]]*5}))

    def test_gate_rejects_reintroduced_social_candidate(self):
        source=item(); approved={'cotton-swab':{source['url']:source}}
        row=dict(id='cotton-swab',url=source['url'],product_name='IQOS 綿棒100本',metric='piece',price=1000,unit_price=10)
        self.assertTrue(gate.validate_recommendations({'items':[row]},approved))
        row['product_name']=source['name'];self.assertFalse(gate.validate_recommendations({'items':[row]},approved))
        row['price']=1;self.assertTrue(gate.validate_recommendations({'items':[row]},approved))

    def test_empty_today_overwrites_old_recommendations(self):
        now=datetime(2026,9,23,6,tzinfo=ZoneInfo('Asia/Tokyo'))
        text=deals.render_page([],now)
        self.assertIn('品質条件を満たす買い候補が不足',text)
        self.assertNotIn('買い候補5選',text)
        self.assertEqual(deals.build_social([],now)['text'],'')
        with tempfile.TemporaryDirectory() as directory:
            old=deals.HOME; deals.HOME=Path(directory)/'index.html'
            try:
                deals.HOME.write_text('<main><section id="today-deals-entry">IQOS</section></main>')
                deals.inject_home([],now)
                self.assertNotIn('IQOS',deals.HOME.read_text())
            finally: deals.HOME=old

    def test_search_examples_do_not_reuse_general_trends(self):
        html=chips.replace_product_chips('<div class="examples"><button>ノートパソコン</button></div>')
        self.assertEqual(len(chips.checked_suggestions()),8)
        for word in ['ノートパソコン','プレゼント','パナソニック','UES']:
            self.assertNotIn(word,html)
        self.assertIn('アタックZERO',html)

    def test_home_ranking_is_only_an_entry(self):
        html=ranking.build_block([{'name':'GPU','rakuten':'https://hb.afl.rakuten.co.jp/test'}])
        self.assertNotIn('GPU',html)
        self.assertIn('href="trends/"',html)


def category_case(category_id, good, bad):
    def test(self):
        self.assertTrue(quality.category_is_suitable(category_id,good),good)
        self.assertFalse(quality.category_is_suitable(category_id,bad),bad)
    return test

assert set(CASES)==set(quality.REQUIRED)
for category_id,(good,bad) in CASES.items():
    setattr(ProductQualityTests,'test_category_'+category_id.replace('-','_'),category_case(category_id,good,bad))
