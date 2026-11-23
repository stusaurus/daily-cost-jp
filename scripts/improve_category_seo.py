"""Strengthen SEO for generated category pages without changing ranking logic."""
from __future__ import annotations

import html
import json
import re
import urllib.parse
from pathlib import Path

SITE_DIR = Path("site")
DATA_PATH = SITE_DIR / "data.json"
BASE_URL = "https://stusaurus.github.io/daily-cost-jp/"

CATEGORIES = {
    "toilet-paper": ("トイレットペーパー", "🧻", "トイレットペーパー"),
    "tissue": ("ティッシュ", "📦", "ティッシュペーパー"),
    "laundry": ("洗濯洗剤", "🧴", "洗濯洗剤"),
    "dish": ("食器用洗剤", "🍽️", "食器用洗剤"),
    "water": ("水・ミネラルウォーター", "💧", "ミネラルウォーター"),
    "coffee": ("コーヒー", "☕", "コーヒー"),
    "softener": ("柔軟剤", "🌸", "柔軟剤"),
    "shampoo": ("シャンプー", "🧴", "シャンプー"),
    "conditioner": ("コンディショナー", "🫧", "コンディショナー・リンス"),
    "body-soap": ("ボディソープ", "🛁", "ボディソープ"),
    "hand-soap": ("ハンドソープ", "🧼", "ハンドソープ"),
    "bath-cleaner": ("お風呂用洗剤", "🛀", "お風呂用洗剤・バスクリーナー"),
    "toilet-cleaner": ("トイレ用洗剤", "🚽", "トイレ用洗剤"),
    "laundry-bleach": ("衣料用漂白剤", "✨", "衣料用漂白剤"),
    "mouthwash": ("マウスウォッシュ", "🦷", "マウスウォッシュ・洗口液"),
    "paper-towel": ("ペーパータオル", "🧻", "ペーパータオル"),
    "garbage-bag-45l": ("45Lゴミ袋", "🗑️", "45Lゴミ袋・ごみ袋"),
    "mask": ("不織布マスク", "😷", "不織布マスク"),
    "toothbrush": ("歯ブラシ", "🪥", "歯ブラシ"),
    "cotton-swab": ("綿棒", "◽", "綿棒"),
    "floor-sheet": ("フローリングシート", "🧹", "フローリングシート"),
    "toothpaste": ("歯磨き粉", "🦷", "歯磨き粉"),
    "wet-wipes": ("除菌ウェットティッシュ", "🧻", "除菌ウェットティッシュ"),
    "kitchen-paper": ("キッチンペーパー", "🍳", "クッキングペーパー"),
    "sink-net": ("排水口ネット（キッチン用）", "🧽", "キッチン用水切りネット"),
}

# Search Console supports the existing priority-page queries. The four new
# categories have no post-release GSC demand proof yet: their copy below is
# factual buyer guidance, not a claim of measured search demand.
SEARCH_TARGETS = {
    "toilet-paper": {
        "title": "トイレットペーパーはいくらなら安い？送料込みの値段比較",
        "h1": "トイレットペーパーはいくらなら安い？値段比較と目安",
        "lead": "トイレットペーパーの送料込み価格を比較。シングル・ダブルを分けて10mあたりの単価にそろえ、1ロールの価格や巻きの長さも確認しながら、店頭と楽天のどちらで買うか判断できます。",
        "heading": "トイレットペーパーの値段はどこが安い？比較のコツ",
        "intent_note": "「トイレットペーパー いくらなら安い」「最安値」「値段比較」で探す場合も、ロール数だけでなく、シングル・ダブルを分けて10mあたりの単価をそろえると長巻き・倍巻きも比較しやすくなります。",
        "description": "トイレットペーパーはいくらなら安い？楽天市場の送料込み商品を毎朝更新し、シングル・ダブル別の10m単価と1ロール価格で比較。長巻き・倍巻きも同じ基準で確認できます。",
    },
    "laundry": {
        "title": "洗濯洗剤の安い店は？楽天送料込み単価ランキングと掲載店比較",
        "h1": "洗濯洗剤はどこが安い？楽天掲載店と単価を比較",
        "lead": "洗濯洗剤の楽天掲載商品を{comparison_unit}あたりで安い順に比較。ショップ名・詰め替え個数・送料込み支払総額も確認できます。店頭の実売価格や楽天全店舗の最安値を保証するものではありません。",
        "heading": "洗濯洗剤はどこが安い？価格とコスパの比較ポイント",
        "intent_note": "「洗濯洗剤 どこが安い」「値段比較」「安い店」で探すときは、本体・詰め替え・大容量で支払総額が違うため、{comparison_unit}あたりの単価だけでなく、セット数と必要量も確認してください。",
        "description": "洗濯洗剤の楽天掲載商品を送料込み{comparison_unit}あたりの単価で比較。詰め替え・大容量のセット個数、ショップ名、送料込み支払総額を確認。濃縮タイプは1回の使用量にも注意。楽天全店の最安値は保証しません。",
    },
    "tissue": {
        "title": "ティッシュの値段比較｜5箱セット・まとめ買いの送料込み単価",
        "h1": "ティッシュの値段比較｜どこが安い？",
        "lead": "ティッシュの楽天掲載商品を100組あたりで比較。5箱セットとまとめ買いの箱数・組数・送料込み支払総額を確認し、店頭価格と比べられます。",
        "description": "ティッシュの楽天掲載商品を送料込み100組あたりで値段比較。5箱セットとまとめ買いの箱数・1箱の組数・支払総額を確認。価格と購入条件は販売店で再確認してください。",
        "heading": "ティッシュはどこが安い？価格を比べるポイント",
        "intent_note": "「ティッシュ どこが安い」「ティッシュ 値段比較」で探すときは、箱数だけでなく1箱の組数を確認し、100組あたりの価格にそろえると、200組や250組の商品も比較しやすくなります。",
    },
    "toothpaste": {
        "title": "歯磨き粉の値段比較｜送料込み100g単価と支払総額",
        "h1": "歯磨き粉はいくらなら安い？100g単価で比較",
        "lead": "歯磨き粉は容量がgで確認できる商品を、送料込みの100gあたりで比較。まとめ買いの本数と支払総額も確認できます。容量がml表記のものはgに推定換算しません。",
        "description": "歯磨き粉の楽天掲載候補を、送料込み100g単価と支払総額で比較。gで内容量が確定した商品だけを対象にし、まとめ買いの数量も確認できます。",
        "heading": "歯磨き粉の値段はどう比べる？",
        "intent_note": "1本あたりの値段だけでは小容量と大容量を比べにくいため、g表記の内容量と本数から100g単価を確認します。成分や使用目的は価格とは別に選んでください。",
    },
    "wet-wipes": {
        "title": "除菌ウェットティッシュの値段比較｜送料込み1枚単価",
        "h1": "除菌ウェットティッシュはどこが安い？1枚単価比較",
        "lead": "除菌ウェットティッシュは枚数が確定した送料込み商品を1枚あたりの価格で比較。パック数と支払総額に加えて、アルコール・ノンアルコールなどの種類も確認してください。",
        "description": "除菌ウェットティッシュの楽天掲載候補を送料込み1枚単価で比較。枚数とパック数が確認できた商品の支払総額を並べ、用途や種類の違いも説明します。",
        "heading": "除菌ウェットティッシュは何枚入りが安い？",
        "intent_note": "80枚入りと複数パックなどは、確認できた合計枚数で1枚単価を算出します。アルコール・ノンアルコールの違いや使用できる場所は、商品表示を確認してください。",
    },
    "kitchen-paper": {
        "title": "キッチンペーパーの値段比較｜1枚単価と送料込み総額",
        "h1": "キッチンペーパーはいくらなら安い？枚数で比較",
        "lead": "キッチンペーパーの送料込み価格を1枚あたりで比較。ロール型も枚数・ロール数・袋数の合計が明記された場合だけ換算し、購入時の支払総額を表示します。",
        "description": "キッチンペーパーを楽天の送料込み1枚単価で比較。ロール・シート型とも合計枚数が明確な商品だけを掲載し、まとめ買いの支払総額を確認できます。",
        "heading": "キッチンペーパーはロール型も1枚単価で比較できる？",
        "intent_note": "1ロールのカット数とロール数・袋数が明記された商品だけ合計枚数を計算します。厚み・大きさ・材質が違うため、1枚単価だけで用途の適合は判断できません。",
    },
    "sink-net": {
        "title": "キッチン排水口ネットの値段比較｜1枚単価・送料込み",
        "h1": "キッチン排水口ネットはどこが安い？1枚単価比較",
        "lead": "キッチン用の排水口・水切りネットを送料込みの1枚あたりの単価で比較。枚数と支払総額に加え、排水口の形・大きさに合う商品か確認してください。",
        "description": "キッチン排水口ネットの送料込み価格を1枚単価で比較。数量の明確な楽天掲載商品を対象に、支払総額とサイズ確認の注意点をまとめます。",
        "heading": "排水口ネットを買うときの枚数とサイズの見方",
        "intent_note": "50枚入りと複数袋セットは合計枚数で単価を計算します。浅型・深型やネットの寸法が合わないと使いにくいため、価格とは別に対応サイズを確認してください。",
    },
}

METRIC_LABELS = {
    "roll": "1ロール", "box": "1箱", "pack": "1パック", "100g": "100g",
    "100ml": "100ml", "1L": "1L", "sheet": "1枚", "piece": "1本",
}



PRIORITY_LINKS = [
    ("tissue", "ティッシュの値段比較"),
    ("toilet-paper", "トイレットペーパーはいくらなら安い？"),
    ("laundry", "洗濯洗剤はどこが安い？"),
]
# Neighboring, already published comparison pages, not claims of GSC popularity.
RELATED_CATEGORY_LINKS = {
    "toothpaste": [("toothbrush", "歯ブラシ"), ("mouthwash", "マウスウォッシュ")],
    "wet-wipes": [("paper-towel", "ペーパータオル"), ("floor-sheet", "フローリングシート")],
    "kitchen-paper": [("paper-towel", "ペーパータオル"), ("dish", "食器用洗剤")],
    "sink-net": [("dish", "食器用洗剤"), ("kitchen-paper", "キッチンペーパー")],
}

def priority_links(current_id: str) -> str:
    related = current_id in RELATED_CATEGORY_LINKS
    choices = RELATED_CATEGORY_LINKS.get(current_id, PRIORITY_LINKS)
    title = "一緒に比較したい日用品" if related else "よく比較されている日用品"
    links = [
        f'<a href="../{slug}/">{html.escape(label)}</a>'
        for slug, label in choices if slug != current_id
    ]
    if not links:
        return ""
    return f'<nav class="search-priority-links" aria-label="{title}"><strong>{title}</strong>' + "".join(links) + '</nav>'


def replace_once(text: str, pattern: str, replacement: str) -> str:
    return re.sub(pattern, replacement, text, count=1, flags=re.DOTALL)


def metric_label(category_id: str, payload: dict) -> str:
    # The paper rankings use normalized comparison units, while catalog.metric
    # retains box/roll for parsing quantities and reference per-package prices.
    if category_id == "tissue":
        return "100組"
    if category_id == "toilet-paper":
        return "シングル・ダブル別の10m"
    data = payload.get("categories", {}).get(category_id, {})
    return METRIC_LABELS.get(data.get("metric"), "同じ単位")


def schema_markup(name: str, category_id: str, description: str, page_name: str) -> str:
    canonical = BASE_URL + f"categories/{category_id}/"
    data = {
        "@context": "https://schema.org",
        "@graph": [
            {"@type": "BreadcrumbList", "itemListElement": [
                {"@type": "ListItem", "position": 1, "name": "日用品コスパ比較", "item": BASE_URL},
                {"@type": "ListItem", "position": 2, "name": "カテゴリ一覧", "item": BASE_URL + "categories/"},
                {"@type": "ListItem", "position": 3, "name": name, "item": canonical},
            ]},
            {"@type": "CollectionPage", "name": page_name, "description": description,
             "url": canonical, "isPartOf": {"@type": "WebSite", "name": "日用品コスパ比較", "url": BASE_URL}},
        ],
    }
    return '<script id="category-seo-schema" type="application/ld+json">' + json.dumps(data, ensure_ascii=False) + "</script>"


def render_search_copy(text: str, label: str) -> str:
    """Fill only the known comparison-unit marker from the validated category label."""
    return text.replace("{comparison_unit}", label)


def toilet_ply_compare_panel(payload: dict) -> str:
    """Two equal, source-verified buying paths with no inferred inventory."""
    from urllib.parse import urlsplit
    from comparison_units import comparison_unit, quantity_label, toilet_ply_length
    from product_quality import filter_items
    from product_display import clean_display_name

    data = payload.get("categories", {}).get("toilet-paper", {})
    groups = data.get("toilet_ply_groups") if isinstance(data, dict) else None
    if not isinstance(groups, dict):
        return ""

    status = data.get("toilet_ply_supply") or {}
    family_status = status.get("families") if isinstance(status, dict) else {}
    family_status = family_status if isinstance(family_status, dict) else {}

    def offer_card(item, label):
        unit = comparison_unit("toilet-paper", item)
        details = toilet_ply_length(item)
        if not unit or unit[0] != label + "10m" or not details:
            return ""
        name = html.escape(clean_display_name(item["name"]))
        url = html.escape(item["url"], quote=True)
        price = int(item["price"])
        length = details[1]
        length_label = f"{length:g}m／ロール"
        quantity = html.escape(quantity_label(item))
        shop = html.escape(str(item.get("shop", "") or "販売店の表記なし"))
        code = html.escape(str(item.get("item_code", "")), quote=True)
        image_url = str(item.get("image") or "")
        image_host = urlsplit(image_url).hostname or ""
        photo = (
            f'<img src="{html.escape(image_url, quote=True)}" alt="" loading="lazy" '
            'width="90" height="90">'
            if image_url.startswith("https://") and
            (image_host == "rakuten.co.jp" or image_host.endswith(".rakuten.co.jp"))
            else '<span aria-hidden="true">🧻</span>'
        )
        return (
            '<article class="toilet-ply-card">'
            f'<div class="toilet-ply-photo">{photo}</div>'
            '<div class="toilet-ply-card-body">'
            f'<h4>{name}</h4>'
            '<strong class="toilet-ply-price">'
            f'<span class="toilet-ply-amount">¥{unit[1]:.2f}</span>'
            f'<span class="toilet-ply-unit">／{label}10m</span>'
            '</strong>'
            f'<p class="toilet-ply-facts">{quantity} ・ {length_label}</p>'
            f'<p class="toilet-ply-total">支払総額 ¥{price:,}（送料込み）</p>'
            f'<p class="toilet-ply-shop">{shop}</p>'
            f'<a class="toilet-ply-buy buy-button" href="{url}" target="_blank" '
            'rel="nofollow sponsored noopener" data-conversion-source="category" '
            f'data-category-id="toilet-paper" data-id="{code}" '
            f'data-product-name="{name}" data-shipping-price="{price}" '
            f'data-unit-price-label="¥{unit[1]:.2f}／{label}10m">'
            f'楽天で{label}の商品を確認する</a>'
            '</div></article>'
        )

    blocks = []
    for key, label in (("single", "シングル"), ("double", "ダブル")):
        raw = groups.get(key, [])
        if not isinstance(raw, list):
            raise ValueError("Malformed toilet-paper family")
        eligible = filter_items("toilet-paper", raw)
        offers = sorted(
            (r for r in eligible if (u := comparison_unit("toilet-paper", r))
             and u[0] == label + "10m"),
            key=lambda r: (comparison_unit("toilet-paper", r)[1], r["price"],
                           str(r.get("item_code", ""))),
        )
        cards = [offer_card(row, label) for row in offers]
        cards = [card for card in cards if card]
        query = urllib.parse.quote("トイレットペーパー " + label)
        if cards:
            # Answer the observed "いくらなら安い" intent with only the
            # cheapest *verified published candidate*, never a market price.
            best = offers[0]
            best_unit = comparison_unit("toilet-paper", best)
            snapshot = (
                '<p class="toilet-ply-price-snapshot" data-offer-count="'
                + str(len(cards)) + '">'
                f'今回確認できた{label}{len(cards)}件の送料込み候補では、'
                f'最も低い単価が<strong>10mあたり ¥{best_unit[1]:.2f}</strong>。'
                f'その商品の支払総額は ¥{best["price"]:,}です。'
                '掲載候補内の数値であり、店頭や楽天全店の相場・最安値ではありません。</p>'
            )
            content = (
                snapshot
                + '<div class="toilet-ply-card-list">' + ''.join(cards[:2]) + '</div>'
                + (f'<details class="toilet-ply-more"><summary>ほかの{label}候補'
                   f'{len(cards) - 2}件を表示</summary>'
                   '<div class="toilet-ply-card-list">' + ''.join(cards[2:]) + '</div>'
                   '</details>' if len(cards) > 2 else '')
            )
        else:
            details = family_status.get(key) or {}
            error_note = (
                "取得が一部失敗しているため、該当商品を確認できませんでした。"
                if details.get("state") == "INCOMPLETE_ACQUISITION"
                else "今回の取得データでは、重ね数・長さ・送料を確認できる候補がありません。"
            )
            content = '<p class="toilet-ply-empty">' + error_note + '</p>'
        blocks.append(
            f'<section class="toilet-ply-group" id="toilet-{key}-offers" '
            f'aria-labelledby="toilet-{key}-heading">'
            f'<h3 id="toilet-{key}-heading">{label}の比較候補（{len(cards)}件）</h3>'
            f'<p class="toilet-ply-desc">{label}同士で10mあたりの価格が安い順。'
            '送料込みで数量が確定した商品のみです。</p>'
            + content
            + f'<a class="toilet-ply-search" href="../../products/?q={query}">'
            f'{label}を商品名でさらに検索する</a>'
            '</section>'
        )
    return (
        '<section class="toilet-ply-compare" aria-labelledby="toilet-ply-heading">'
        '<h2 id="toilet-ply-heading">シングル・ダブルを選んで価格比較</h2>'
        '<p class="toilet-ply-intro">まず種類を選び、10m単価と支払総額を確認。'
        'シングルとダブルでは紙の重ね数が異なるため、両者の安さを直接順位付けしません。</p>'
        '<nav class="toilet-ply-links" aria-label="トイレットペーパーの種類">'
        '<a href="#toilet-single-offers">シングルの比較を見る</a>'
        '<a href="#toilet-double-offers">ダブルの比較を見る</a>'
        '</nav>'
        '<div class="toilet-ply-groups">' + ''.join(blocks) + '</div>'
        '<p class="toilet-ply-caution">表示は取得時点の候補で、楽天市場全体の最安値ではありません。'
        '地域別送料・在庫・クーポンは購入前に楽天で再確認してください。</p>'
        '</section>'
    )


def toilet_ply_availability_note(payload: dict) -> str:
    """Only describe a missing ply when the current ranking has a verified other ply."""
    from comparison_units import comparison_unit

    category = payload.get("categories", {}).get("toilet-paper", {})
    items = category.get("items") if isinstance(category, dict) else None
    if not isinstance(items, list) or not items:
        return ""
    groups = category.get("toilet_ply_groups") if isinstance(category, dict) else None
    eligible = set()
    if isinstance(groups, dict):
        for key, label in (("single", "シングル10m"), ("double", "ダブル10m")):
            if groups.get(key):
                eligible.add(label)
    else:
        for item in items:
            if not isinstance(item, dict):
                continue
            unit = comparison_unit("toilet-paper", item)
            if unit and unit[0] in {"シングル10m", "ダブル10m"}:
                eligible.add(unit[0])
    if len(eligible) != 1:
        return ""
    available = "シングル" if "シングル10m" in eligible else "ダブル"
    missing = "ダブル" if available == "シングル" else "シングル"
    query = urllib.parse.quote("トイレットペーパー " + missing)
    return (
        '<p class="category-ply-availability" role="note">'
        f"今回掲載している比較可能な候補は{available}のみです。"
        f"{missing}の10m単価を確認できた候補は今回の一覧にありません。"
        f"楽天市場に{missing}の商品がないという意味ではありません。"
        f'<a href="../../products/?q={query}">{missing}を商品名で検索する →</a>'
        "</p>"
    )


def relevant_water_cost_route(category_id: str) -> str:
    """Link two distinct, existing utilities for water buyers; never imply a price ranking."""
    if category_id != "water":
        return ""
    return (
        '<aside class="category-related-tool" aria-label="水の年間費用を考える">'
        '<strong>水を買う量だけでなく、1年間の支出も比較する</strong>'
        '<p>このページではペットボトル水の1L単価を比較しています。'
        'ウォーターサーバーとの違いを確かめたい方は、家庭で使う水量・ケース価格・'
        '送料・サーバー月額・電気代・初期費用を入力して、年間支払額を計算できます。</p>'
        '<a href="https://stusaurus.github.io/food-cost-jp/guides/water-server-vs-bottled-water/">'
        'ペットボトルとウォーターサーバーの年間費用を計算する →</a>'
        '</aside>'
    )


def seo_section(category_id: str, name: str, alias: str, label: str) -> str:
    q = urllib.parse.quote(name)
    safe_name, safe_alias, safe_label = html.escape(name), html.escape(alias), html.escape(label)
    target = SEARCH_TARGETS.get(category_id, {})
    heading = html.escape(target.get("heading", f"{name}はどこが安い？比較するときのポイント"))
    intent_note = render_search_copy(target.get("intent_note", ""), label)
    intent_html = f'<p class="search-intent-note">{html.escape(intent_note)}</p>' if intent_note else ""
    return f"""
<section class="category-seo-guide" id="compare-guide">
  <h2>{heading}</h2>
  <p>{safe_alias}は、商品価格だけでは容量や個数の違いで安さを判断しにくいため、このページでは楽天市場で送料込みと確認できた商品を<strong>{safe_label}あたり</strong>にそろえて価格比較しています。</p>
  {intent_html}
  <ul>
    <li><strong>単価で比較：</strong>容量違い・まとめ買いでも{safe_label}あたりに換算</li>
    <li><strong>送料込みを優先：</strong>表示価格だけ安く見える送料別商品を避けて比較</li>
    <li><strong>毎朝更新：</strong>取得できた楽天市場の商品情報をもとに安い順を更新</li>
  </ul>
  <a class="category-search-cta" href="../../products/?q={q}">商品名を指定して楽天の送料込み価格を検索 →</a>
  {relevant_water_cost_route(category_id)}
</section>
"""


PRIORITY_FAQS = {
    "tissue": [
        ("ティッシュはどこが安いか、何を見れば分かりますか？", "箱数だけでなく1箱の組数を確認し、100組あたりの価格で比較します。参考の1箱単価も見ながら、内容量の違いを確かめてください。"),
        ("ティッシュはいくらなら安いですか？", "販売箱数や組数で条件が変わるため、固定の総額ではなく、このページの最新ランキングで100組あたりの単価と送料込み支払総額を確認するのが安全です。"),
    ],
    "toilet-paper": [
        ("トイレットペーパーはいくらなら安いですか？", "ロール数や1ロールの長さが違うため、総額だけで判断せず、シングル・ダブルを分けた10mあたりの単価で比較するのがポイントです。"),
        ("トイレットペーパーの最安値はどう比較しますか？", "送料込みの商品にそろえ、シングル・ダブルを分けて10mあたりの単価を確認します。1ロール価格が安くても巻きが短ければ、同じ長さでは割高になる場合があります。"),
    ],
    "laundry": [
        ("洗濯洗剤はどこが安いか、どう比較しますか？", "本体・詰め替え・大容量で総額が違うため、このページでは{comparison_unit}あたりの単価で比較します。濃縮タイプは1回の使用量も確認すると実際のコストを判断しやすくなります。"),
        ("洗濯洗剤の安い店を探すときの注意点は？", "表示価格だけでなく容量とセット数、送料を確認します。このページでは楽天市場で送料込みと確認できた商品を同じ単位に換算して比較しています。"),
    ],
    "toothpaste": [
        ("歯磨き粉のgとmlはそのまま比較できますか？", "できません。体積と質量は同じ数値ではないため、このランキングは内容量がgで明記された商品の100g単価に限定しています。"),
        ("歯磨き粉は100g単価だけで選べますか？", "価格の比較には役立ちますが、フッ素濃度や薬用成分、使用する人の年齢・目的などは別に商品表示を確認してください。"),
    ],
    "wet-wipes": [
        ("除菌ウェットティッシュのまとめ買いは何を比較しますか？", "1袋の枚数と袋数の両方が確認できる場合だけ合計枚数を求め、1枚単価と送料込み支払総額を確認します。"),
        ("アルコールとノンアルコールは同じ商品ですか？", "種類や用途が異なるため同一商品として扱いません。対応する素材や使用上の注意を購入前に確認してください。"),
    ],
    "kitchen-paper": [
        ("キッチンペーパーのロール型は何枚として数えますか？", "商品名で1ロールのカット数、ロール数、必要な袋数が明記されている場合にだけ合計枚数へ換算します。不明な個数は推測しません。"),
        ("1枚あたりが安ければ、どのキッチンペーパーでも同じですか？", "違います。サイズ・厚み・材質・吸水性などは商品によって異なります。用途に適したものを比較してください。"),
    ],
    "sink-net": [
        ("排水口ネットは1枚単価だけで選べますか？", "枚数から単価は比較できますが、排水口の寸法と浅型・深型などの形状を合わせる必要があります。"),
        ("排水口ネットのセット数はどう数えますか？", "袋ごとの枚数と袋数の双方が確定できた商品だけ合計枚数を使用します。ホルダー付きなど数量・商品構成が曖昧なものはランキング対象外です。"),
    ],
}

def faq_section(category_id: str, name: str, label: str) -> str:
    safe_name, safe_label = html.escape(name), html.escape(label)
    extra = "".join(
        f"<details><summary>{html.escape(q)}</summary><p>{html.escape(render_search_copy(a, label))}</p></details>"
        for q, a in PRIORITY_FAQS.get(category_id, [])
    )
    return f"""
<section class="category-seo-faq" id="category-faq">
  <h2>{safe_name}の価格比較FAQ</h2>
  {extra}
  <details><summary>{safe_name}は何を基準に安い順にしていますか？</summary><p>楽天市場で送料込みと確認でき、商品名から容量や個数を高い確度で読み取れた商品を、{safe_label}あたりの単価に換算して比較しています。</p></details>
  <details><summary>送料はランキング価格に含まれていますか？</summary><p>送料込みの商品を対象に比較しています。クーポンや一部のポイント還元は単価に含めていないため、購入前に楽天市場の商品ページで最終価格をご確認ください。</p></details>
  <details><summary>価格はいつ更新されますか？</summary><p>カテゴリランキングは毎朝自動更新します。特定の商品を今すぐ確認したい場合は、商品名検索からリアルタイムの送料込み購入候補を探せます。</p></details>
</section>
"""

# The final published layout is fingerprinted from scripts/design/laboratory.css.
# The generator's temporary inline CSS is stripped by redesign_laboratory.
CSS = """
<style id="category-seo-style">
.category-seo-guide,.category-seo-faq{margin:18px 0;padding:16px;border:1px solid var(--line);border-radius:14px;background:#fff}
.category-seo-guide h2,.category-seo-faq h2{font-size:18px;line-height:1.4;margin:0 0 9px}
.category-seo-guide p,.category-seo-guide li,.category-seo-faq p{font-size:12px;line-height:1.75;color:#4b5563}
.category-seo-guide ul{margin:10px 0 14px;padding-left:20px}.category-search-cta{display:block;padding:12px 14px;border-radius:11px;background:#252525;color:#fff;text-decoration:none;text-align:center;font-size:12px;font-weight:900}
.category-ply-availability{margin:10px 0 0;padding:11px 13px;border-left:3px solid #897665;background:#f7f3ef;font-size:12px;line-height:1.7;color:#484039}.category-ply-availability a{display:inline-block;padding:8px 0;font-weight:800;color:#252525;text-decoration:underline}
.search-priority-links{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin:14px 0;padding:12px;border:1px solid var(--line);border-radius:12px;background:#fff}.search-priority-links strong{font-size:11px}.search-priority-links a{font-size:11px;font-weight:800;color:#252525}.category-seo-faq details{border-top:1px solid var(--line);padding:10px 0}.category-seo-faq details:first-of-type{border-top:0}.category-seo-faq summary{cursor:pointer;font-size:12px;font-weight:800;line-height:1.55}.category-seo-faq p{margin:7px 0 0}
</style>
"""


# Keep styles for the cross-site water decision route off the protected priority pages.
WATER_ROUTE_CSS = """<style id="water-related-tool-style">
.category-related-tool{margin:14px 0 0;padding:13px;border:1px solid #d5e2e1;border-radius:12px;background:#f4faf9}
.category-related-tool strong{display:block;font-size:14px;line-height:1.6;color:#203e3a}
.category-related-tool p{margin:5px 0 8px;font-size:13px;line-height:1.7}
.category-related-tool a{display:inline-block;min-height:44px;padding:10px 0;color:#1e4e49;text-decoration:underline;font-size:13px;font-weight:800}
</style>"""


def enhance_page(category_id: str, name: str, emoji: str, alias: str, payload: dict) -> bool:
    path = SITE_DIR / "categories" / category_id / "index.html"
    if not path.exists(): return False
    markup = path.read_text(encoding="utf-8")
    label = metric_label(category_id, payload)
    target = SEARCH_TARGETS.get(category_id, {})
    base_title = f"{name}の安い順比較｜{label}単価・楽天送料込みランキング"
    title = target.get("title", base_title) + " | 日用品コスパ比較"
    h1 = target.get("h1", f"{name}の安い順・単価ランキング")
    lead = render_search_copy(target.get("lead", f"楽天市場の{name}を送料込み価格で{label}あたりに換算し、今日の安い順に比較します。"), label)
    description = render_search_copy(target.get("description") or (target.get("lead", f"{alias}を楽天市場の送料込み価格で{label}あたりに換算し、安い順に比較。") + " 毎朝更新のランキングとリアルタイム価格検索で購入候補を確認できます。"), label)

    markup = replace_once(markup, r"<title>.*?</title>", f"<title>{html.escape(title)}</title>")
    markup = replace_once(markup, r'<meta name="description" content="[^"]*">', f'<meta name="description" content="{html.escape(description, quote=True)}">')
    markup = replace_once(markup, r"<h1>.*?</h1>", f"<h1>{emoji} {html.escape(h1)}</h1>")
    markup = replace_once(markup, r'<p class="lead">.*?</p>', f'<p class="lead">{html.escape(lead)}</p>')
    if category_id == "toilet-paper":
        note = toilet_ply_availability_note(payload)
        panel = toilet_ply_compare_panel(payload)
        if note or panel:
            lead_markup = f'<p class="lead">{html.escape(lead)}</p>'
            if markup.count(lead_markup) != 1:
                raise ValueError("Cannot place ply comparison safely")
            markup = markup.replace(lead_markup, lead_markup + "\n" + panel + "\n" + note, 1)

    if 'id="category-seo-style"' not in markup:
        markup = markup.replace("</head>", CSS + "\n" + schema_markup(name, category_id, description, h1) + "\n</head>", 1)
    if category_id == "water" and 'id="water-related-tool-style"' not in markup:
        if "</head>" not in markup:
            raise ValueError("Missing head for water route style")
        markup = markup.replace("</head>", WATER_ROUTE_CSS + "\n</head>", 1)
    if 'id="compare-guide"' not in markup:
        summary_end = markup.find("</div>", markup.find('class="category-summary"'))
        if summary_end != -1:
            insert_at = summary_end + len("</div>")
            markup = markup[:insert_at] + "\n" + seo_section(category_id, name, alias, label) + markup[insert_at:]
        else:
            markup = markup.replace('<main class="container">', '<main class="container">\n' + seo_section(category_id, name, alias, label), 1)
    if 'class="search-priority-links"' not in markup:
        marker = '<section class="related-categories">'
        links = priority_links(category_id)
        if links:
            if marker in markup: markup = markup.replace(marker, links + "\n" + marker, 1)
            else: markup = markup.replace("</main>", links + "\n</main>", 1)
    if 'id="category-faq"' not in markup:
        marker = '<section class="related-categories">'
        if marker in markup: markup = markup.replace(marker, faq_section(category_id, name, label) + "\n" + marker, 1)
        else: markup = markup.replace("</main>", faq_section(category_id, name, label) + "\n</main>", 1)
    path.write_text(markup, encoding="utf-8")
    return True


def main() -> None:
    if not DATA_PATH.exists(): raise SystemExit("site/data.json not found")
    payload = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    changed = sum(1 for category_id, (name, emoji, alias) in CATEGORIES.items() if enhance_page(category_id, name, emoji, alias, payload))
    print(f"Strengthened category SEO on {changed}/{len(CATEGORIES)} pages.")

if __name__ == "__main__": main()
