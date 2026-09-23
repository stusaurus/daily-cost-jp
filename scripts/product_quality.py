"""Shared, fail-closed eligibility for all 21 unit-price categories.

Use product titles (not shop names or descriptions) as evidence. Unknown or
ambiguous products are omitted; a missing candidate is safer than a cheap guess.
This module has no network, credentials or build-time side effects.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import math
import re
import statistics
from urllib.parse import urlsplit

from sale_quantity import ambiguous_quantity, normalize

VERSION = 1

# Each group must have at least one match. Brands alone are not enough where
# the brand sells several kinds of goods (e.g. さらさ detergent AND softener).
REQUIRED = {
    'toilet-paper': (r'トイレット(?:ペーパー|ロール)|コア[・ー]?ユース|ワンタッチコアレス',),
    'tissue': (r'ティッシュペーパー|ティシュペーパー|ボックスティッシュ|箱ティッシュ|(?:ソフト)?パックティッシュ|ポケットティッシュ',),
    'laundry': (r'洗濯(?:用)?洗剤|衣料用洗剤|洗濯用.*(?:石けん|石鹸)|アタック|アリエール|ボールド|エマール',),
    'dish': (r'食器(?:用)?\s*洗剤|台所(?:用)?\s*洗剤|キュキュット|(?:除菌)?ジョイ|チャーミー',),
    'water': (r'ミネラルウォーター|天然水|ナチュラルウォーター|クリスタルガイザー|飲料水|軟水',),
    'coffee': (r'コーヒー|珈琲', r'豆|粉|焙煎'),
    'softener': (r'柔軟剤',),
    'shampoo': (r'シャンプー',),
    'conditioner': (r'コンディショナー|リンス',),
    'body-soap': (r'ボディ[ー]?(?:ソープ|ウォッシュ)',),
    'hand-soap': (r'ハンドソープ|手洗い(?:石けん|石鹸)',),
    'bath-cleaner': (r'お?風呂|浴室|バスタブ|バスマジックリン|バスクリーナー', r'洗剤|クリーナー|クレンジング|マジックリン'),
    'toilet-cleaner': (r'トイレ|便器', r'洗剤|クリーナー|マジックリン|サンポール'),
    'laundry-bleach': (r'衣料用漂白剤|衣類用漂白剤|ワイドハイター|ブライト.*(?:漂白|strong)|酸素系漂白剤|過炭酸ナトリウム',),
    'mouthwash': (r'マウスウォッシュ|洗口液|液体歯磨|リステリン|デンタルリンス',),
    'paper-towel': (r'ペーパー(?:ハンド)?タオル|タオルペーパー|手拭きペーパー',),
    'garbage-bag-45l': (r'45\s*(?:l|リットル)', r'ゴミ袋|ごみ袋|ポリ袋'),
    'mask': (r'マスク', r'不織布'),
    'toothbrush': (r'歯ブラシ|ハブラシ|はぶらし',),
    'cotton-swab': (r'綿棒',),
    'floor-sheet': (r'フローリング|フロア|床掃除|床用|ワイパー', r'シート'),
}

EXCLUDED = {
    'toilet-paper': r'ホルダー|カバー|収納|ペーパーポット|トイレブラシ|シングル.*ダブル|ダブル.*シングル',
    'tissue': r'ウェット|ウエット|おしり|手口|除菌シート|ペーパータオル|キッチンペーパー|ティッシュ(?:ケース|ボックス|カバー|ホルダー)|シートバック|収納ポケット',
    'laundry': r'柔軟剤(?!不要|不使用|なし)|衣料用漂白剤|ワイドハイター|ブライト\s*strong|洗濯槽|食器|台所|ジェルボール|ポッド|洗剤シート',
    'dish': r'ハンドソープ|洗濯|食洗機|食器洗い(?:乾燥)?機|ディッシュウォッシャー|リンス剤',
    'water': r'炭酸|スパークリング|ウォーターサーバー|水筒|浄水器|化粧水|精製水|サプリ|ペット用|犬用|猫用',
    'coffee': r'コーヒーメーカー|ドリッパー|フィルター|コーヒーミル|マグカップ|インスタント|スティック|ドリップバッグ|ドリップパック|カプセル|生豆|コーヒーかす|ボトルコーヒー',
    'softener': r'柔軟剤(?:不要|不使用|なし)|柔軟剤入り|洗濯(?:用)?(?:洗剤|石けん)|芳香剤|香りづけ|香り付け|ビーズ',
    'shampoo': r'コンディショナー|トリートメント|リンス|シャンプーブラシ|犬用|猫用|ペット用|ドライシャンプー|洗車',
    'conditioner': r'シャンプー|トリートメント|ブラシ|犬用|猫用|ペット用|デンタルリンス',
    'body-soap': r'シャンプー|ハンドソープ|トリートメント|コンディショナー|スポンジ|タオル|犬用|猫用|ペット用',
    'hand-soap': r'シャンプー|ボディソープ|手指消毒|消毒液|除菌ジェル|食器用',
    'bath-cleaner': r'ブラシ|スポンジ|バスソルト|入浴剤|防カビ剤|浴槽コーティング|排水口|排水管',
    'toilet-cleaner': r'ブラシ|便座シート|トイレットペーパー|収納|コーティング剤|スタンプ|芳香剤|消臭剤|洗浄シート|お掃除シート',
    'laundry-bleach': r'キッチン|台所|食器|排水口|カビ取り|洗濯槽専用',
    'mouthwash': r'歯磨き粉|歯ブラシ|舌ブラシ|洗浄器|携帯容器',
    'paper-towel': r'ホルダー|スタンド|ディスペンサー|布タオル|キッチンペーパー|ロールタオル',
    'garbage-bag-45l': r'ゴミ箱|ごみ箱|ホルダー|スタンド|収納|圧縮袋',
    'mask': r'ケース|ストラップ|スプレー|マスクフレーム|収納|フェイスパック|シートマスク|美容液|(?<!織)布マスク|ウレタン',
    'toothbrush': r'電動|替えブラシ|替ブラシ|交換ブラシ|ケース|ホルダー|スタンド|歯磨き粉|犬用|猫用|ペット用',
    'cotton-swab': r'iqos|アイコス|\bglo\b|グロー|ploom|プルーム|電子(?:タバコ|たばこ)|加熱式|たばこ|タバコ|クリーニング|cleaning|工業用|精密機器|耳かき|耳掻き|粘着|ネバ|吸引|合成ゴム|再利用|綿棒入れ',
    'floor-sheet': r'ワイパー本体|モップ本体|ホルダー|収納|フロアタイル|床材|置くだけ|置き敷き|接着剤|大理石|石目|床\s*タイル|補修|ワックスシート',
}

# "ケース販売" is a legitimate bulk package, unlike a case/empty container.
ACCESSORY = re.compile(r'ディスペンサー|詰[め]?替[え]?用?ボトル|シャンプーボトル|ソープボトル|空(?:の)?(?:ボトル|容器)|ボトルのみ|容器のみ|ケースのみ|収納ケース|詰[め]?替[え]?容器(?!スプーンなし)|(?:綿棒|マスク|ペーパー|歯ブラシ)(?:用)?ケース', re.I)
MIXED = re.compile(r'選べるセット|お試しセット|福袋|詰め合わせ|アソート|本体\s*[+＋&]\s*(?:詰替|詰め替え)|(?:詰替|詰め替え)\s*[+＋&]\s*本体', re.I)
COUNT_UNITS = {
    'toilet-paper': {'ロール': 'roll', '巻': 'roll'},
    'tissue': {'箱': 'box', 'パック': 'pack', '個': 'pack'},
    'paper-towel': {'枚': 'sheet'}, 'garbage-bag-45l': {'枚': 'sheet'},
    'mask': {'枚': 'sheet'}, 'toothbrush': {'本': 'piece'}, 'cotton-swab': {'本': 'piece'},
    'floor-sheet': {'枚': 'sheet'},
}


def category_rejection(category_id, title):
    if category_id not in REQUIRED:
        return 'unknown_category'
    text = normalize(title).lower()
    if not text.strip():
        return 'missing_title'
    if ambiguous_quantity(text):
        return 'selectable_quantity'
    if re.search(r'ふるさと納税|返礼品', text):
        return 'donation'
    if ACCESSORY.search(text):
        return 'accessory'
    if MIXED.search(text):
        return 'mixed_bundle'
    if re.search(EXCLUDED[category_id], text, re.I):
        return 'wrong_use_or_type'
    if not all(re.search(group, text, re.I) for group in REQUIRED[category_id]):
        return 'missing_category_evidence'
    return None


def category_is_suitable(category_id, title):
    return category_rejection(category_id, title) is None


def parsed_quantity(category_id, title):
    if category_id in COUNT_UNITS:
        return safer_parse_count_quantity(title, COUNT_UNITS[category_id])
    return safer_parse_measure_quantity(title, category_id if category_id in ('water', 'coffee') else 'measure')


def item_rejection(category_id, item):
    reason = category_rejection(category_id, item.get('name', ''))
    if reason:
        return reason
    try:
        price, unit = float(item['price']), float(item['unit_price'])
        confidence = float(item['confidence'])
    except (KeyError, TypeError, ValueError):
        return 'missing_price_or_quantity'
    if not all(math.isfinite(n) and n > 0 for n in (price, unit, confidence)) or confidence < .84:
        return 'invalid_price_or_confidence'
    if item.get('postage') != '送料込み':
        return 'unconfirmed_shipping'
    url = urlsplit(str(item.get('url') or ''))
    if url.scheme != 'https' or not (url.hostname or '').endswith('.rakuten.co.jp'):
        return 'invalid_destination'
    parsed = parsed_quantity(category_id, item.get('name', ''))
    if not parsed:
        return 'ambiguous_quantity'
    if parsed['metric'] != item.get('metric'):
        return 'unit_mismatch'
    if not math.isclose(price / parsed['quantity'], unit, rel_tol=.0001, abs_tol=.0001):
        return 'quantity_price_mismatch'
    return None


def filter_items(category_id, items, report=None):
    """Recheck even cached/downstream input; never trust an old quality flag."""
    valid, rejected = [], []
    for item in items:
        reason = item_rejection(category_id, item)
        if reason:
            rejected.append({'name': item.get('name', ''), 'reason': reason})
        else:
            valid.append({**item, 'category_id': category_id, 'quality_version': VERSION})
    # Remove isolated extreme low prices before they can become a #1 or baseline.
    groups = defaultdict(list)
    for item in valid:
        groups[item['metric']].append(item)
    outlier_ids = set()
    for group in groups.values():
        ordered = sorted(group, key=lambda p: p['unit_price'])
        if len(ordered) < 3:
            continue
        median = statistics.median(p['unit_price'] for p in ordered)
        for i, item in enumerate(ordered[:-1]):
            if item['unit_price'] < median * .2 and item['unit_price'] < ordered[i + 1]['unit_price'] * .5:
                outlier_ids.add(id(item))
                rejected.append({'name': item['name'], 'reason': 'isolated_price_outlier'})
    valid = [p for p in valid if id(p) not in outlier_ids]
    if report is not None:
        report[category_id] = {'checked': len(items), 'accepted': len(valid),
            'reasons': dict(Counter(p['reason'] for p in rejected)), 'rejected': rejected}
    return valid


def to_base_amount(amount, unit):
    unit = unit.lower()
    amount = float(amount)
    if unit == "kg":
        return "weight", amount * 1000
    if unit == "g":
        return "weight", amount
    if unit == "l":
        return "volume", amount * 1000
    if unit == "ml":
        return "volume", amount
    return None, None


def result_from_total(kind, total, category_kind, confidence, evidence):
    if not total or total <= 0:
        return None
    if kind == "weight":
        metric = "100g"
        quantity = total / 100
    else:
        metric = "1L" if category_kind == "water" else "100ml"
        quantity = total / (1000 if metric == "1L" else 100)

    if category_kind == "coffee" and metric != "100g":
        return None
    if quantity <= 0:
        return None
    return {
        "metric": metric,
        "quantity": quantity,
        "confidence": confidence,
        "evidence": evidence,
    }


def safer_parse_measure_quantity(title, category_kind):
    """Reject variant titles unless all visible capacity evidence agrees."""
    text = normalize(title)
    if ambiguous_quantity(title):
        return None
    # Stock/offer limits (先着100本限定) are not the quantity being sold.
    text = re.sub(r"(?:先着|限定)\s*\d+\s*(?:個|袋|本|パック|セット)(?:限定)?", "", text)

    explicit_matches = list(re.finditer(
        r"(\d+(?:\.\d+)?)\s*(kg|g|ml|l)\s*x\s*(\d+)",
        text,
        flags=re.IGNORECASE,
    ))
    if explicit_matches:
        totals = []
        kinds = []
        for match in explicit_matches:
            kind, base = to_base_amount(match.group(1), match.group(2))
            totals.append(base * int(match.group(3)))
            kinds.append(kind)
        if len(set(kinds)) != 1 or max(totals) - min(totals) > 0.001:
            return None

        chosen = explicit_matches[0]
        chosen_kind = kinds[0]
        chosen_total = totals[0]

        all_measures = re.findall(
            r"(\d+(?:\.\d+)?)\s*(kg|g|ml|l)",
            text,
            flags=re.IGNORECASE,
        )
        visible_bases = []
        for amount, unit in all_measures:
            kind, base = to_base_amount(amount, unit)
            if kind == chosen_kind:
                visible_bases.append(base)
        explicit_base = to_base_amount(chosen.group(1), chosen.group(2))[1]
        if any(abs(base - explicit_base) > 0.001 and abs(base - chosen_total) > 0.001 for base in visible_bases):
            return None

        return result_from_total(
            chosen_kind,
            chosen_total,
            category_kind,
            0.99,
            chosen.group(0),
        )

    all_measures = re.findall(
        r"(\d+(?:\.\d+)?)\s*(kg|g|ml|l)",
        text,
        flags=re.IGNORECASE,
    )
    if len(all_measures) != 1:
        return None

    amount, unit = all_measures[0]
    kind, base = to_base_amount(amount, unit)
    if not kind or not base:
        return None

    pack_counts = [
        int(value)
        for value, pack_unit in re.findall(
            r"(\d+)\s*(個|袋|本|パック|セット)",
            text,
            flags=re.IGNORECASE,
        )
        if int(value) > 1
    ]
    if len(pack_counts) == 1:
        total = base * pack_counts[0]
        evidence = f"{pack_counts[0]}個相当 × {amount}{unit}"
        confidence = 0.94
    elif len(pack_counts) == 0:
        total = base
        evidence = f"{amount}{unit}"
        confidence = 0.88
    else:
        return None

    return result_from_total(kind, total, category_kind, confidence, evidence)


def safer_parse_count_quantity(title, allowed_units):
    text = normalize(title)
    text = re.sub(r"(?:先着|限定)\s*\d+\s*(?:個|袋|本|パック|セット)(?:限定)?", "", text)
    if ambiguous_quantity(title):
        return None
    units_re = "|".join(re.escape(unit) for unit in allowed_units)

    explicit_matches = list(re.finditer(
        rf"(\d+(?:\.\d+)?)\s*({units_re})(?:入り|入)?\s*x\s*(\d+)",
        text,
        flags=re.IGNORECASE,
    ))
    if explicit_matches:
        totals = [float(m.group(1)) * int(m.group(3)) for m in explicit_matches]
        if max(totals) - min(totals) > 0.001:
            return None
        total = totals[0]
        # Accept a repeated total (5箱×12パック=60箱), reject a variant count
        # elsewhere (20枚×1袋 ... 51枚) even when one explicit pack matched.
        visible = [float(m.group(1)) for m in re.finditer(rf"(\d+(?:\.\d+)?)\s*({units_re})", text)]
        bases = {float(m.group(1)) for m in explicit_matches}
        if any(v not in bases and v != total for v in visible):
            # Tissue outer packs can occur in the allowed unit list as well.
            outer = {float(m.group(3)) for m in explicit_matches}
            if any(v not in bases | outer | {total} for v in visible):
                return None
        if total > 0 and float(total).is_integer():
            return {
                "metric": allowed_units[explicit_matches[0].group(2)],
                "quantity": total,
                "confidence": 0.99,
                "evidence": explicit_matches[0].group(0),
            }

    singles = list(re.finditer(
        rf"(\d+(?:\.\d+)?)\s*({units_re})",
        text,
        flags=re.IGNORECASE,
    ))
    if not singles:
        return None

    values = [float(m.group(1)) for m in singles]
    if len(set(values)) > 1:
        return None

    total = values[0]
    if total > 0 and total.is_integer():
        return {
            "metric": allowed_units[singles[0].group(2)],
            "quantity": total,
            "confidence": 0.88,
            "evidence": singles[0].group(0),
        }
    return None
