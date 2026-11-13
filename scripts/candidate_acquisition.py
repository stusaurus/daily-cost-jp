"""Bounded candidate expansion; every search uses the same quality gate."""
from __future__ import annotations

from urllib.parse import parse_qs, urlsplit
from product_quality import filter_items

# Concrete consumable searches, never arbitrary trends. These only add input;
# they do not grant category eligibility or waive quantity/shipping checks.
SUPPLEMENTAL_QUERIES = {
    'toilet-paper': ('トイレットペーパー ダブル 12ロール', 'トイレットペーパー ダブル 48ロール', 'トイレットペーパー シングル 48ロール'),
    'tissue': ('ボックスティッシュ 5箱', 'スコッティ ティッシュペーパー', 'エリエール ティッシュペーパー'),
    'laundry': ('アタックZERO 詰め替え', 'さらさ 洗濯洗剤', 'アリエール 液体洗剤'),
    'dish': ('キュキュット 詰め替え', 'ジョイ 食器用洗剤', 'チャーミー 食器用洗剤'),
    'water': ('天然水 2L 12本', 'ミネラルウォーター 500ml 24本'),
    'coffee': ('コーヒー豆 500g', 'コーヒー粉 1kg'),
    'softener': ('さらさ 柔軟剤', 'ランドリン 柔軟剤', 'ラボン 柔軟剤'),
    'shampoo': ('メリット シャンプー 詰め替え', 'いち髪 シャンプー', 'ミノン シャンプー'),
    'conditioner': ('メリット コンディショナー 詰め替え', 'いち髪 コンディショナー', 'ミノン コンディショナー'),
    'body-soap': ('ビオレ ボディソープ 詰め替え', 'ミヨシ 泡のボディソープ', 'ダヴ ボディウォッシュ'),
    'hand-soap': ('キレイキレイ ハンドソープ', 'ビオレu ハンドソープ', 'ミューズ 泡ハンドソープ 詰め替え'),
    'bath-cleaner': ('バスマジックリン 詰め替え', 'バスタブクレンジング 800ml'),
    'toilet-cleaner': ('トイレマジックリン 洗剤 詰め替え', 'サンポール 500ml', 'まめピカ トイレクリーナー'),
    'laundry-bleach': ('ワイドハイターEX 4.5L', 'ブライト 衣料用漂白剤'),
    'mouthwash': ('リステリン 1000ml', 'マウスウォッシュ 500ml'),
    'paper-towel': ('ペーパータオル 200枚', 'タウパー ペーパータオル'),
    'garbage-bag-45l': ('ゴミ袋 45L 100枚', 'ごみ袋 45リットル 半透明', 'ポリ袋 45L 100枚'),
    'mask': ('不織布マスク 50枚', '不織布マスク 30枚'),
    'toothbrush': ('歯ブラシ 10本', '歯ブラシ 20本'),
    'cotton-swab': ('紙軸 綿棒 200本', '抗菌 綿棒', 'ベビー 綿棒 200本'),
    'floor-sheet': ('フローリング ウェットシート 20枚', 'クイックルワイパー 取り替え シート', 'フローリング ドライシート 30枚'),
}
TARGET = 5
MAX_REQUESTS = 5

# A fixed total-count threshold is not sufficient for products sold as two
# incompatible specifications. These bounded, specification-specific searches
# run only while that family has fewer than three validated candidates.
TOILET_PLY_TARGET = 3
TOILET_PLY_MAX_REQUESTS = 6
TOILET_PLY_QUERIES = (
    ("double", "トイレットペーパー ダブル 12ロール"),
    ("single", "トイレットペーパー シングル 12ロール"),
    ("double", "トイレットペーパー ダブル 48ロール"),
    ("single", "トイレットペーパー シングル 48ロール"),
)


def max_requests_for(category_id):
    return TOILET_PLY_MAX_REQUESTS if category_id == "toilet-paper" else MAX_REQUESTS



def identity(item):
    if item.get('item_code'):
        return ('code', item['item_code'])
    url = str(item.get('url') or '')
    parts = urlsplit(url)
    destination = parse_qs(parts.query).get('pc', [url])[0]
    direct = urlsplit(destination)
    if direct.hostname in ('item.rakuten.co.jp', 'www.rakuten.co.jp'):
        return ('url', direct.hostname, direct.path.rstrip('/'))
    return ('fallback', item.get('name', ''), item.get('shop', ''), url)


def acquire(category, fetch_page, normalize_item, choose_ranked, sleep):
    """Keep successful pages on optional failures, dedupe and preserve a bounded search budget.

    The first two requests mirror the old acquisition, making the same-run
    baseline measurable. The toilet-paper family has a separate bounded request
    budget to cover both specifications. Only the
    original first-page failure is fatal; an optional failed request never
    discards existing safe products. No URL/secrets from exceptions are logged.
    """
    items, seen, requests = [], set(), []
    duplicates = 0

    def ranked_count():
        return len(choose_ranked(filter_items(category['id'], items))[1])

    def append_page(query, page, supplementary=False):
        nonlocal duplicates
        if requests:
            sleep(1.15)
        request_category = {**category, 'keyword': query, '_supplementary': supplementary}
        record = {'query': query, 'page': page, 'supplementary': supplementary}
        requests.append(record)
        try:
            raw_items = fetch_page(request_category, page)
        except Exception as exc:
            record.update(received=0, error=type(exc).__name__)
            if len(requests) == 1:
                raise
            return
        record['received'] = len(raw_items)
        for raw in raw_items:
            item = normalize_item(raw, category)
            key = identity(item)
            if key in seen:
                duplicates += 1
                continue
            seen.add(key)
            items.append(item)
        record['unique_total'] = len(items)
        record['ranked_total'] = ranked_count()

    append_page(category['keyword'], 1)
    if ranked_count() < TARGET:
        append_page(category['keyword'], 2)
    baseline = {}
    filter_items(category['id'], items, baseline)
    baseline = baseline[category['id']]
    baseline['ranked'] = ranked_count()
    baseline.pop('rejected')  # Full final exclusions are in quality-report.json.

    # Tissue ranking can reach five safe *bulk* items and stop before showing
    # an affordable first-purchase pack. Probe exactly one optional 5-box
    # search when the current safe supply contains no 1–10-box offer.
    # This never relaxes the shared shipping/quantity matcher.
    if category['id'] == 'tissue' and len(requests) < MAX_REQUESTS:
        from tissue_buying_quantity import choose_small_tissue_offer
        if choose_small_tissue_offer(items) is None:
            append_page(SUPPLEMENTAL_QUERIES['tissue'][0], 1, supplementary=True)

    if category['id'] == 'toilet-paper':
        from comparison_units import comparison_unit

        def verified_by_ply():
            result = {"single": 0, "double": 0}
            for row in filter_items("toilet-paper", items):
                unit = comparison_unit("toilet-paper", row)
                if unit and unit[0] in ("シングル10m", "ダブル10m"):
                    result["single" if unit[0] == "シングル10m" else "double"] += 1
            return result

        for family, query in TOILET_PLY_QUERIES:
            if len(requests) >= max_requests_for(category['id']):
                break
            if verified_by_ply()[family] >= TOILET_PLY_TARGET:
                continue
            append_page(query, 1, supplementary=True)
    else:
        for query in SUPPLEMENTAL_QUERIES.get(category['id'], ()):
            if ranked_count() >= TARGET or len(requests) >= MAX_REQUESTS:
                break
            if query != category['keyword'] and not any(r['query'] == query and r['page'] == 1 for r in requests):
                append_page(query, 1, supplementary=True)
    return items, {'baseline': baseline, 'requests': requests,
                   'received': sum(r.get('received', 0) for r in requests),
                   'duplicates_removed': duplicates, 'unique': len(items),
                   'ranked': ranked_count()}
