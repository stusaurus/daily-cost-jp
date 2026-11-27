"""Shared, fail-closed eligibility for all configured unit-price categories.

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
    'coffee': (r'コーヒー|珈琲', r'豆|粉|焙煎|[細粗中]挽き'),
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
    'cotton-swab': (r'綿棒', r'衛生|紙軸|抗菌|滅菌|耳そうじ|耳掃除|耳の|メイク|化粧|赤ちゃん|ベビー'),
    'floor-sheet': (r'フローリング|フロア|床掃除|床用|ワイパー', r'シート'),
    'toothpaste': (r'歯磨き粉|歯みがき粉|歯磨き|歯みがき|ハミガキ|デンタルペースト',),
    'wet-wipes': (r'ウェット(?:ティッシュ|シート)|ウエット(?:ティッシュ|シート)', r'除菌|アルコール|衛生'),
    'kitchen-paper': (r'キッチンペーパー|キッチンタオル|クッキングペーパー',),
    'sink-net': (r'排水口|排水溝|水切り', r'ネット', r'キッチン|台所|シンク|流し台|排水口|排水溝|三角コーナー'),
}

EXCLUDED = {
    'toilet-paper': r'ホルダー|カバー|収納|ペーパーポット|トイレブラシ|シングル.*ダブル|ダブル.*シングル',
    'tissue': r'ウェット|ウエット|おしり|手口|除菌シート|ペーパータオル|キッチンペーパー|ティッシュ(?:ケース|ボックス|カバー|ホルダー)|シートバック|収納ポケット',
    'laundry': r'柔軟剤(?!不要|不使用|なし)|衣料用漂白剤|ワイドハイター|ブライト\s*strong|洗濯槽|食器|台所|ジェルボール|ポッド|洗剤シート',
    'dish': r'ペット用|犬用|猫用|ハンドソープ|洗濯|食洗機|食器洗い(?:乾燥)?機|ディッシュウォッシャー|リンス剤',
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
    'cotton-swab': r'iqos|アイコス|\bglo\b|グロー|ploom|プルーム|電子(?:タバコ|たばこ)|加熱式|たばこ|タバコ|クリーニング|cleaning|工業用|精密機器|耳かき|耳掻き|粘着|ネバ|吸引|合成ゴム|再利用|綿棒入れ|歯ブラシ|ハブラシ|ペット|犬|猫|加湿|給水|吸水芯|フィルター',
    'floor-sheet': r'ワイパー本体|モップ本体|ホルダー|収納|フロアタイル|床材|置くだけ|置き敷き|接着剤|大理石|石目|床\s*タイル|補修|ワックスシート',
    'toothpaste': r'歯ブラシ|ハブラシ|替えブラシ|歯間ブラシ|マウスウォッシュ|洗口液|デンタルリンス|携帯容器|チューブホルダー|詰め替え容器|犬用|猫用|ペット用|歯磨きシート',
    'wet-wipes': r'おしりふき|お尻拭き|手口ふき|赤ちゃん|ベビー|ペット|犬用|猫用|フローリング|床|トイレ|便座|キッチン用|台所用|浴室|クリーナー本体|ケース|詰替用ケース|タオル本体',
    'kitchen-paper': r'クッキングシート|オーブンシート|ワックスペーパー|ベーキングシート|ペーパータオル|ホルダー|スタンド|布(?:巾|製|タオル)|フキン|ふきん|台ふき|専用容器|(?:収納|保管|持ち運び)ケース|ケース(?:のみ|付き|本体)',
    'sink-net': r'排水口(?:カゴ|かご|カバー|ふた|フタ|蓋)|ネット(?:用)?ホルダー|ホルダー|スタンド|バスケット|ゴミ受け|ごみ受け|水切り(?:かご|カゴ|ラック|器)|ステンレス鋼|吸盤|排水口フィルターホルダー|ストレーナー本体|ブラシ|パイプクリーナー|洗剤|浴室|お風呂|洗面|洗濯機|トイレ|三角コーナー本体|ケース|収納',
}

# "ケース販売" is a legitimate bulk package, unlike a case/empty container.
ACCESSORY = re.compile(r'ディスペンサー|詰[め]?替[え]?用?ボトル|シャンプーボトル|ソープボトル|空(?:の)?(?:ボトル|容器)|ボトルのみ|容器のみ|ケースのみ|収納ケース|詰[め]?替[え]?容器(?!スプーンなし)|(?:綿棒|マスク|ペーパー|歯ブラシ)(?:用)?ケース|加湿器|(?:給水|吸水)\s*芯|交換用(?:フィルター|カートリッジ)|コットンフィルター', re.I)
MIXED = re.compile(r'選べるセット|お試しセット|福袋|詰め合わせ|アソート|本体\s*[+＋&]\s*(?:詰替|詰め替え)|(?:詰替|詰め替え)\s*[+＋&]\s*本体', re.I)
COUNT_UNITS = {
    'toilet-paper': {'ロール': 'roll', '巻': 'roll'},
    'tissue': {'箱': 'box', 'パック': 'pack', '個': 'pack'},
    'paper-towel': {'枚': 'sheet'}, 'garbage-bag-45l': {'枚': 'sheet'},
    'mask': {'枚': 'sheet'}, 'toothbrush': {'本': 'piece'}, 'cotton-swab': {'本': 'piece'},
    'floor-sheet': {'枚': 'sheet'},
    'wet-wipes': {'枚': 'sheet'}, 'kitchen-paper': {'枚': 'sheet', 'カット': 'sheet'},
    'sink-net': {'枚': 'sheet'},
}


def explicit_tissue_box_total(title):
    """A stated box total corroborated by exactly one explicit pack product."""
    text=normalize(title)
    if ambiguous_quantity(title) or re.search(r'選べ|選択|ポリ袋|レジ袋|空箱',text):
        return None
    matches=list(re.finditer(r'(?<![\d.])(\d+)個パック\s*x\s*(\d+)セット\s*合計\s*(\d+)箱',text))
    if len(matches)!=1:return None
    match=matches[0];inner,outer,total=map(int,match.groups())
    counts=re.findall(r'(\d+(?:\.\d+)?)\s*(個|パック|セット|箱)',text)
    if any('.' in n for n,unit in counts) or re.search(r'x\s*\d',text[match.end():],re.I):return None
    visible=[(int(n),unit) for n,unit in counts]
    if visible!=[(inner,'個'),(outer,'セット'),(total,'箱')] or min(inner,outer,total)<=0 or inner*outer!=total:
        return None
    return {'metric':'box','quantity':float(total),'confidence':0.99,'evidence':match.group(0)}


def explicit_kitchen_paper_sheet_total(title):
    """Only a fully stated sheet × roll × outer-pack product has a total.

    Reject implicit case sizes and more than one set of sheet/roll evidence.
    This is the same parser used by both acquisition and publication gates.
    """
    text = normalize(title).replace('ロ−ル', 'ロール').replace('ロ－ル', 'ロール')
    if ambiguous_quantity(title):
        return None
    pattern = (r'(?<![\d.])(\d+)\s*(枚|カット)\s*x\s*'
               r'(\d+)\s*ロール\s*x\s*(\d+)\s*(袋|パック|セット|個)?')
    matches = list(re.finditer(pattern, text, re.I))
    if len(matches) != 1:
        return None
    match = matches[0]
    per, rolls, packs = int(match[1]), int(match[3]), int(match[4])
    if not all(0 < n <= 10000 for n in (per, rolls, packs)):
        return None
    remainder = text[match.end():]
    if not match[5] and not re.match(r'\s*(?:ケース(?:販売)?|袋|パック|セット|個)', remainder):
        return None
    if re.search(r'x\s*\d+', remainder, re.I):
        return None
    if len(re.findall(r'\d+\s*(?:枚|カット)', text)) != 1:
        return None
    if len(re.findall(r'\d+\s*(?:ロール|巻)', text)) != 1:
        return None
    # An extra explicit pack count would create a second possible sale total.
    if len(re.findall(r'(?<!\d)\d+\s*(?:袋|パック|セット|個)', text)) > 1:
        return None
    total = per * rolls * packs
    if total > 100000:
        return None
    return {'metric': 'sheet', 'quantity': float(total),
            'confidence': 0.99, 'evidence': match.group(0)}


def kitchen_roll_package(title):
    """Return sheets per roll, rolls per retail pack and packs per sale."""
    text = normalize(title).lower().replace("ロ−ル", "ロール").replace("ロ-ル", "ロール")
    text = re.sub(r"(?<![\d.])[12]\s*枚重ね", "", text)
    if ambiguous_quantity(title):
        return None
    case_text = re.sub(r"(ロール\s*x\s*\d+)\s*ケース販売", r"\1", text)
    cases = re.findall(r"(?<![\d.])(\d+(?:\.\d+)?)\s*(?:箱|ケース)", case_text)
    if len(cases) > 1 or cases and cases != ["1"]:
        return None
    explicit = explicit_kitchen_paper_sheet_total(text)
    if explicit:
        per, rolls = map(int, re.match(r"(\d+)\s*(?:枚|カット)\s*x\s*(\d+)", explicit["evidence"]).groups())
        return per, rolls, int(explicit["quantity"]) // (per * rolls)
    # Sellers also state the case total first, followed by rolls per pack and pack count.
    case = r"(?<![\d.])(\d+)\s*(?:枚|カット)\s+(\d+)\s*ロール\s*\(\s*(\d+)\s*ロール\s*x\s*(\d+)\s*(?:パック|袋)\s*\)"
    single = r"(?<![\d.])(\d+)\s*(?:枚|カット)\s*x\s*(\d+)\s*ロール"
    if match := re.search(case, text):
        per, total_rolls, rolls, packs = map(int, match.groups())
        if total_rolls != rolls * packs:
            return None
    elif match := re.search(single, text):
        per, rolls = map(int, match.groups())
        packs = 1
    else:
        return None
    rest = text[:match.start()] + text[match.end():]
    if (not 0 < per * rolls * packs <= 100000 or not 1 <= packs <= 120
            or re.search(r"x\s*\d|\d+\s*(?:枚|カット|ロール|巻|袋|パック|個|箱|セット|ケース)", rest)
            or (packs == 1 and re.search(r"ケース|複数|まとめ買い|セット", rest))):
        return None
    return per, rolls, packs


def category_rejection(category_id, title):
    if category_id not in REQUIRED:
        return 'unknown_category'
    text = normalize(title).lower()
    if not text.strip():
        return 'missing_title'
    if ambiguous_quantity(text):
        return 'selectable_quantity'
    # Some Attack ZERO offers omit a literal 'choose a type' warning while
    # enumerating three mutually exclusive formulas in one listing. The
    # currently observed Iris Plaza six-pack offers exactly this choice;
    # quantities can differ between selected types (1460g vs 1540g).
    # A title alone cannot bind the stated price to a specific type/capacity.
    if (category_id == 'laundry' and re.search(r'アタック\s*zero', text, re.I)
            and all(token in text for token in ('レギュラー', '部屋干し', 'ドラム式専用'))):
        return 'selectable_type_variant'
    if re.search(r'ふるさと納税|返礼品', text):
        return 'donation'
    if re.search(r'法人(?:様)?(?:限定|専用)|個人宅(?:配送|配達)?不可', text):
        return 'restricted_purchase'
    if re.search(r'中古|定期(?:購入|便|コース)|初回(?:限定|価格)|クーポン(?:適用|利用|使用)(?:後|で)|クーポン後(?:価格|の価格)', text):
        return 'conditional_or_used_price'
    if category_id == 'garbage-bag-45l':
        volumes = re.findall(r'(?<![\d.])(\d+(?:\.\d+)?)\s*l(?![a-z])', text)
        if not volumes or any(float(volume) != 45 for volume in volumes):
            return 'wrong_bag_capacity'
    if ACCESSORY.search(text):
        return 'accessory'
    if MIXED.search(text):
        return 'mixed_bundle'
    category_text = text.replace('ケース販売', '') if category_id == 'sink-net' else text
    if re.search(EXCLUDED[category_id], category_text, re.I):
        return 'wrong_use_or_type'
    # Three new sheet categories measure the number of *individual sheets*.
    # Titles such as "80枚 3パック" are not 80 sheets total. Without a
    # multiplication sign, reject rather than invent an incorrect unit price.
    if category_id in ('wet-wipes', 'kitchen-paper', 'sink-net'):
        sheet_term = r'(?:枚|カット)' if category_id == 'kitchen-paper' else r'枚'
        has_explicit_sheet_count = bool(re.search(rf'\d+\s*{sheet_term}', text))
        outer_packs = re.findall(r'(?<!\d)(?:[2-9]|[1-9]\d+)\s*(?:袋|パック|個|セット|p\b|ケース)', text)
        # 80枚 x 3袋 and 100カット x 2ロール are countable. But
        # "80枚 x 3P", two nested packs and "80枚 3パック" are not.
        has_proven_multiplier = bool(re.search(
            rf'\d+\s*{sheet_term}(?:入|入り)?\s*x\s*\d+(?:ロール|巻|袋|パック|個|セット)?(?![\da-z])', text, re.I))
        if not has_explicit_sheet_count:
            return 'missing_sheet_count'
        nested = kitchen_roll_package(title) if category_id == 'kitchen-paper' else None
        if not nested and (len(outer_packs) > 1 or len(re.findall(r'x\s*\d+', text, re.I)) > 1
                or re.search(r'\d+\s*ケース', text)):
            return 'multiple_unverified_pack_levels'
        if (category_id == 'kitchen-paper' and not nested
                and re.search(r'(?:ロール|ロ−ル|巻)', text)):
            # Each roll's stated sheets must have an explicit multiplication.
            if not re.search(r'\d+\s*(?:枚|カット)\s*x\s*\d+\s*(?:ロール|ロ−ル|巻)', text):
                return 'roll_sheet_count_unconfirmed'
            if outer_packs:
                return 'multiple_unverified_pack_levels'
        if outer_packs and not has_proven_multiplier and not nested:
            return 'package_multiplier_unconfirmed'
    if category_id == 'wet-wipes' and (
            (re.search(r'ノンアルコール', text)
             and re.search(r'(?<!ノン)アルコール', text))
            or (re.search(r'wts[- ]?60n', text, re.I)
                and re.search(r'wts[- ]?60a', text, re.I))):
        # A selectable alcohol formula cannot be bound to a fixed offer.
        return 'selectable_type_variant'
    # A mass-based dentifrice page must not rank millilitres as grams.
    evidence=all(re.search(group,text,re.I) for group in REQUIRED[category_id])
    if category_id=='tissue' and not evidence:
        # Literal product type plus explicit pairs and corroborated box total;
        # never recognize a product from its brand name alone.
        boxes = re.findall(r'(?<![\d.])\d+\s*箱', text)
        simple_boxes = len(boxes) == 1 and not re.search(r'合計|ポリ袋|レジ袋|空箱|箱なし', text)
        evidence = bool(re.search(r'ティシュー|ティシュ|ティッシュ', text)
                        and re.search(r'(?<![\d.])\d+\s*組', text)
                        and (simple_boxes or explicit_tissue_box_total(text)))
    if not evidence:
        return 'missing_category_evidence'
    return None


def category_is_suitable(category_id, title):
    return category_rejection(category_id, title) is None


def parsed_quantity(category_id, title):
    if category_id in COUNT_UNITS:
        return safer_parse_count_quantity(title, COUNT_UNITS[category_id])
    parsed = safer_parse_measure_quantity(title, category_id if category_id in ('water', 'coffee') else 'measure')
    if category_id == 'toothpaste' and parsed and parsed['metric'] != '100g':
        return None
    return parsed


def item_rejection(category_id, item):
    reason = category_rejection(category_id, item.get('name', ''))
    if reason:
        return reason
    # Diagnose parsing failures explicitly; acceptance rules are unchanged.
    parsed = parsed_quantity(category_id, item.get('name', ''))
    if not parsed:
        return 'ambiguous_quantity'
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
    if allowed_units==COUNT_UNITS['tissue']:
        explicit=explicit_tissue_box_total(title)
        if explicit:return explicit
    if allowed_units==COUNT_UNITS['kitchen-paper']:
        if package := kitchen_roll_package(title):
            per, rolls, packs = package
            return {"metric": "sheet", "quantity": float(per * rolls * packs),
                    "confidence": 0.99, "evidence": f"{per}枚x{rolls}ロールx{packs}袋"}
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
