"""Render the marketplace comparison as an optional layer over the Rakuten build."""
import hashlib
import html
import json
import os
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from marketplace_offers import Product, cheapest_offer, price_unit, rakuten_offer, yahoo_offer
from marketplace_discovery import discover
from marketplace_finder import add_finder, anchor
from marketplace_rakuten import refresh_exact
from yahoo_shopping import YahooShopping, YahooUnavailable

MARKER = 'id="marketplace-comparison"'
MAIN = '<main class="container" id="lab-content">'
NAV_MARKER = 'id="marketplace-navigation"'
FRAGMENT = "#marketplace-comparison"
ANCHOR = '<section class="purchase-answer lab-answer" id="buying-answer">'
CREDIT = """<!-- Begin Yahoo! JAPAN Web Services Attribution Snippet -->
<span style="margin:15px 15px 15px 15px"><a href="https://developer.yahoo.co.jp/sitemap/">Webサービス by Yahoo! JAPAN</a></span>
<!-- End Yahoo! JAPAN Web Services Attribution Snippet -->"""

REFILL = r"(?:詰|つ)め?(?:替|か)え?"
ATTACK_ZERO = r"アタック\s*(?:zero|ゼロ)"
PRODUCTS = {
    "toilet-paper": (
        Product("4901750227401", "スコッティ フラワーパック 3倍長持ち ダブル", 12, "ロール",
                (r"スコッティ", r"フラワーパック", r"3倍", r"ダブル"), r"シングル|2倍|4倍",
                rakuten_items=("rakuten24:11044376",), roll_length_m=75),
        Product("4902727005237", "丸富製紙 ワンタッチコアレス トイレットペーパー シングル", 6, "ロール",
                (r"ワンタッチ", r"コアレス|芯なし", r"シングル"), r"ダブル|細芯",
                rakuten_items=("ec-try:10001076",), roll_length_m=150),
    ),
    "tissue": (
        Product("4901750417352", "スコッティ ティッシュペーパー ホワイト 1箱200組", 5, "箱",
                (r"スコッティ|scottie", r"ティッ?シュ|ティシュー"), r"フラワー|カシミヤ|ウェルネス|法人限定",
                tissue_pairs=200, rakuten_evidence=(("kyoto23:10001789", "/kyoto23/10001789"),
                                                    ("irisplaza-r:10109543", "/irisplaza-r/7162877"))),
    ),
    "water": (
        Product("4986919990020", "温泉水99 1.9L ペットボトル", 1900, "ml",
                (r"温泉水\s*99", r"ペットボトル"), r"炭酸|硬水|蛇口",
                rakuten_evidence=(("onsensui99:10000186", "/onsensui99/2lx12_cook"),), bottles_per_case=6),
        Product("9000009987990", "クリスタルガイザー エコボトル 正規輸入品", 500, "ml",
                (r"クリスタルガイザー", r"エコボトル", r"正規輸入品"), r"並行輸入|ラベルレス|オランチャ",
                rakuten_evidence=(("kenkocom:11316966", "/kenkocom/e300670h"),)),
        Product("4571461292779", "水想い ナチュラルミネラルウォーター ラベルレス", 2000, "ml",
                (r"水想い", r"ラベルレス", r"天然水|ナチュラルミネラルウォーター"), r"炭酸|硬水",
                rakuten_items=("mizuomoi:10000004",)),
    ),
    "laundry": (
        Product("4901301440815", "アタックZERO 部屋干し 詰め替え", 2000, "g",
                (ATTACK_ZERO, REFILL, r"部屋\s*干し(?!臭)"), r"ドラム式|レギュラー|業務用"),
        Product("4901301466235", "アタックZERO ドラム式専用 詰め替え", 2300, "g",
                (ATTACK_ZERO, REFILL, r"ドラム式(?:洗濯機)?専用"), r"部屋\s*干し(?!臭)|レギュラー|業務用"),
        Product("4987176304834", "さらさ 液体洗剤 詰め替え", 1490, "g",
                (r"さらさ", REFILL, r"洗(?:濯|たく)(?:用)?洗剤|衣(?:料|類)用洗剤|洗剤ジェル"),
                r"柔軟剤(?!不使用|なし|不要)|部屋干し専用"),
    ),
    "softener": (
        Product("4987176184566", "さらさ 柔軟剤 詰め替え", 1350, "ml",
                (r"さらさ", REFILL, r"柔軟剤"), r"洗(?:濯|たく)(?:用)?洗剤|洗剤ジェル"),
    ),
    "dish": (
        Product("4901301429940", "キュキュット オレンジの香り 詰め替え", 1380, "ml",
                (r"キュキュット", r"オレンジ", REFILL),
                r"クリア除菌|マスカット|グレープフルーツ|レモン|無香|ヴァーベナ|本体"),
        Product("4901301360489", "キュキュット クリア除菌 業務用", 4500, "ml",
                (r"キュキュット", r"クリア除菌"), r"オレンジ|グレープフルーツ|レモン|微香|食洗機",
                rakuten_items=("k-relight:10006053",)),
    ),
    "shampoo": (
        Product("4987767624297", "コラージュフルフルネクスト うるおいなめらか 詰め替え", 280, "ml",
                (r"コラージュ\s*フルフル", r"ネクスト", r"シャンプー", r"うるおいなめらか", REFILL),
                r"すっきりさらさら|本体", rakuten_items=("koyama-p:10010152",)),
        Product("4987767624280", "コラージュフルフルネクスト すっきりさらさら 詰め替え", 280, "ml",
                (r"コラージュ\s*フルフル", r"ネクスト", r"シャンプー", r"すっきりさらさら", REFILL),
                r"うるおいなめらか|本体", rakuten_items=("koyama-p:10010151",)),
    ),
    "conditioner": (
        Product("4987107631077", "ミノン 薬用コンディショナー 詰め替え", 380, "ml",
                (r"ミノン|minon", r"薬用\s*コンディショナー", REFILL), r"本体|全身",
                rakuten_items=("tenmi-drug-store:10002589",)),
        Product("4987107631060", "ミノン 薬用コンディショナー 本体", 450, "ml",
                (r"ミノン|minon", r"薬用\s*コンディショナー"), REFILL + r"|全身",
                rakuten_items=("tokitomecosme:10003569",)),
    ),
    "body-soap": (
        Product("4901301033109", "花王 ビオレu ボディウォッシュ 液体 業務用", 10000, "ml",
                (r"ビオレ\s*u", r"ボディ[ー]?(?:ソープ|ウ[ォオ]ッシュ)"), r"泡で出|泡タイプ|無香料|本体",
                rakuten_evidence=(("daily-shop:10000218", "/daily-shop/10000218"),
                                   ("potch7:10002491", "/potch7/10002491"))),
        Product("4901301342898", "ビオレu 泡で出てくるボディウォッシュ 詰め替え", 480, "ml",
                (r"ビオレ\s*u", r"泡で出てくる", r"ボディ", REFILL),
                r"本体|しっとりすべすべタイプ|香りが選べる|おまけ",
                rakuten_items=("beautyeveryday:10000589",)),
    ),
    "hand-soap": (
        Product("4903301181613", "キレイキレイ 薬用泡ハンドソープ 業務用", 4000, "ml",
                (r"キレイキレイ", r"泡\s*ハンドソープ"), r"フルーツミックス|フローラル|無香|本体",
                rakuten_items=("k-relight:10000768",)),
        Product("4903301022527", "キレイキレイ 薬用泡ハンドソープ 業務用", 10000, "ml",
                (r"キレイキレイ", r"泡\s*ハンドソープ"), r"フルーツミックス|フローラル|無香|本体",
                rakuten_items=("k-relight:10000748",)),
    ),
    "bath-cleaner": (
        Product("4903301302674", "ルックプラス バスタブクレンジング 銀イオンプラス 詰め替え", 800, "ml",
                (r"ルック\s*プラス", r"バスタブクレンジング", r"銀イオン", REFILL),
                r"本体|クリアシトラス|フローラル",
                rakuten_evidence=(("mamababy:10183134", "/mamababy/7174479"),
                                   ("kurashikenkou:10198648", "/kurashikenkou/7174478"),
                                   ("l-plus:10225372", "/l-plus/7174478"),
                                   ("unidy:11142443", "/unidy/7174477"),
                                   ("k-home:10076749", "/k-home/7174477"),
                                   ("kurashikenkou:10198646", "/kurashikenkou/7174476"))),
    ),
    "mouthwash": (
        Product("4580132341036", "プロフレッシュ オーラルリンス 正規輸入品", 500, "ml",
                (r"プロフレッシュ|profresh", r"オーラルリンス|マウスウォッシュ"),
                r"並行輸入|トライアル|ミニ|タングスクレーパー付",
                rakuten_evidence=(("kenkocom:10267503", "/kenkocom/p317450h"),
                                   ("alpha-net:10000004", "/alpha-net/020-prf-0013"))),
    ),
    "paper-towel": (
        Product("4902092776497", "タウパー ライズ M 中判 200枚", 200, "枚",
                (r"タウパー|towper", r"ライズ", r"中判|\bm\s*サイズ"), r"小判|大判|ダブル",
                rakuten_evidence=(("daily-shop:10000130", "/daily-shop/10000130"),)),
        Product("4970570444213", "イットコライトタオル L200 ハード 中判 200枚", 200, "枚",
                (r"イットコライトタオル", r"l\s*200", r"ハード"), r"小判|ダブル|ソフト",
                rakuten_items=("ec-try:10001150",)),
    ),
    "garbage-bag-45l": (
        Product("4562345603538", "サンキョウプラテック KN-53 45L 半透明 0.015mm厚", 10, "枚",
                (r"\bkn-53\b", r"45\s*l", r"半透明", r"0\.015\s*mm",
                 r"65\s*x\s*80\s*cm"), r"乳白|45号",
                rakuten_evidence=(("poly-stadium:10000059", "/poly-stadium/k-53"),)),
    ),
    "laundry-bleach": (
        Product("4901301327338", "ワイドハイター EXパワー 液体 業務用", 4500, "ml",
                (r"ワイドハイター", r"ex\s*パワー", r"業務用"), r"粉末|pro|詰め合わせ",
                rakuten_items=("k-relight:10000733", "k-relight:10000734")),
    ),
    "toothbrush": (
        Product("4562189961023", "Ci ミクリン M ふつう ワンタフト歯ブラシ", 1, "本",
                (r"ミクリン|miclin", r"ワンタフト", r"ふつう|普通|\bm\b"), r"やわらか|ハード|2種",
                rakuten_items=("kzstore:10000883",)),
    ),
    "cotton-swab": (
        Product("4976558005568", "綿棒 コットン100％ 紙軸 200本入り", 200, "本",
                (r"綿棒", r"紙軸"), r"黒綿棒|ベビー|スパイラル",
                rakuten_items=("wagonsale-kanahashi:10005405", "wagonsale-kanahashi:10005404")),
    ),
    "toothpaste": (
        Product("4987977000584", "シュミテクト 歯周病ケア 100g 1450ppm", 100, "g",
                (r"シュミテクト", r"歯周病ケア", r"1450\s*ppm"),
                r"コンプリート|ホワイトニング|歯周病ダブルケア",
                rakuten_evidence=(("good-item:10002278", "/good-item/co-124-10set"),
                                   ("good-item:10000966", "/good-item/co-124"))),
    ),
    "floor-sheet": (
        Product("4903320165267", "水の激落ちくん 超厚ウエット フローリングシート", 20, "枚",
                (r"激落ち", r"フローリング", r"ウェット|ウエット", r"超厚"), r"ドライ|除菌タイプ",
                rakuten_items=("lecdirect:10002500",)),
        Product("4957434002857", "フローリング ウェットシート デコボコ", 20, "枚",
                (r"フローリング", r"ウェット|ウエット", r"デコボコ|でこぼこ|凹凸"), r"ドライ|ロング",
                rakuten_items=("wagonsale-kanahashi:10005955", "wagonsale-kanahashi:10005954",
                               "wagonsale-kanahashi:10003232", "wagonsale-kanahashi:10003670",
                               "wagonsale-kanahashi:10003669")),
    ),
    "wet-wipes": (
        Product("4957434009009", "昭和紙工 ノンアルコール除菌ウェットティッシュ", 80, "枚",
                (r"ノンアルコール", r"ウェットティッシュ|ウエットティッシュ", r"除菌"), r"厚手|大判"),
    ),
    "kitchen-paper": (
        Product("4901301369260", "花王 CHEF たっぷり吸収 M 100枚×2ロール", 200, "枚",
                (r"シェフ|chef", r"たっぷり吸収", r"\bm(?:\s*サイズ)?\b|中判"), r"プレミアム|\bl\s*サイズ",
                rakuten_evidence=(("livingplaza:10006445", "/livingplaza/10006445"),), kitchen_rolls=2),
        Product("4901301377036", "花王 CHEF プレミアム L 100枚×2ロール", 200, "枚",
                (r"シェフ|chef", r"プレミアム", r"\bl(?:\s*サイズ)?\b|大判"), r"たっぷり吸収|\bm\s*サイズ",
                rakuten_evidence=(("livingplaza:10003988", "/livingplaza/10003988"),), kitchen_rolls=2),
    ),
    "sink-net": (
        Product("4902493442984", "ボンスター ごみシャット 浅型 ストッキング水切りネット M-298", 50, "枚",
                (r"浅型", r"ストッキング", r"ボンスター|ごみシャット|m[- ]?298"), r"深型|三角コーナー兼用",
                rakuten_items=("bnetshop39:10002985",)),
        Product("4560309850233", "アドグッド 浅型排水口用 水切りネット", 50, "枚",
                (r"浅型", r"水切りネット", r"アドグッド|addgood|クラレ"), r"深型|三角コーナー兼用",
                rakuten_items=("drugpure:10237712",)),
    ),
    "toilet-cleaner": (
        Product("4901301424938", "トイレマジックリン エレガントローズ 詰め替え", 300, "ml",
                (r"トイレ\s*マジックリン", r"エレガント\s*ローズ", REFILL),
                r"ローズ以外|フレッシュハーブ|シトラス|ミント|本体"),
    ),
    "coffee": (
        Product("4901201157592", "UCC 職人の珈琲 深いコクのスペシャルブレンド コーヒー粉", 280, "g",
                (r"職人の珈琲", r"深いコク", r"スペシャルブレンド"),
                r"豆のまま|挽き方|ドリップバッグ|ワンドリップ|インスタント|カフェインレス|アソート",
                rakuten_evidence=(("kusuriaoki-r:10051762", "/kusuriaoki-r/60000000015799"),)),
    ),
    "mask": (
        Product("4901957214853", "フィッティ 7DAYSマスク EXプラス 不織布 ふつう ホワイト", 60, "枚",
                (r"フィッティ|fitty", r"7\s*days|7デイズ", r"ex\s*(?:プラス|\+)", r"ふつう|普通", r"ホワイト|白"),
                r"小さめ|大きめ|やや大き|大きい|学童|子供|子ども|キッズ|ピンク|黒|ブラック|グレー|選択|立体(?:型|マスク)",
                rakuten_evidence=(("kzstore:10000862", "/kzstore/4901957214853"),)),
    ),
}

EXACT_RAKUTEN_CATEGORIES = {"coffee", "mask"}

NAV_CSS = """<style id="marketplace-navigation-style">
#marketplace-navigation{margin:18px 0;padding:12px 15px;border:1px solid #cadfd6;border-radius:10px;background:#f1f8f5;color:#173c31}
#marketplace-navigation h2{margin:0 0 6px;font-size:16px;line-height:1.5}
.marketplace-navigation-links{display:flex;flex-wrap:wrap;gap:6px 10px}
.marketplace-navigation-link{display:inline-flex;align-items:center;min-height:44px;padding:6px 10px;
  border:1px solid #457d68;border-radius:6px;background:white;color:#104b3b;text-decoration:none;font-weight:650;font-size:14px}
.marketplace-navigation-link:hover{text-decoration:underline;background:#e4f2eb;color:#104b3b}
</style>"""
MARKETPLACES = {"rakuten": "楽天市場", "yahoo": "Yahoo!ショッピング"}
CSS = """<style id="marketplace-comparison-style">
#marketplace-comparison{padding:clamp(14px,3vw,26px);margin:24px 0;border:1px solid #cadfd6;border-radius:18px;background:#f1f8f5;color:#173c31}
#marketplace-comparison h2{margin:0 0 8px;font-size:clamp(21px,3vw,27px);line-height:1.35}
#marketplace-comparison p{margin:6px 0;line-height:1.65}
.marketplace-products{display:grid;gap:14px;margin:16px 0}
.marketplace-product{background:white;border:1px solid #d8e4de;border-radius:12px;padding:14px;min-width:0}
.marketplace-product h3{margin:0 0 4px;font-size:17px;line-height:1.4}
.marketplace-totals{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));column-gap:8px;margin:10px 0}
.marketplace-totals div{display:contents}
.marketplace-totals dt,.marketplace-totals dd{background:#f2f6f3;min-width:0;overflow-wrap:anywhere}
.marketplace-totals dt{grid-row:1;padding:7px 8px 0;border-radius:6px 6px 0 0;font-size:12px;line-height:1.35}
.marketplace-totals dd{grid-row:2;padding:2px 8px 7px;border-radius:0 0 6px 6px;margin:0;font-size:clamp(15px,2.5vw,20px);font-weight:750}
.marketplace-totals div:first-child>*{grid-column:1}
.marketplace-totals div:last-child>*{grid-column:2}
.marketplace-totals .marketplace-leading-total>*{background:#d9eee3;color:#104b3b}
.marketplace-prices{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;margin-top:12px}
.marketplace-offer{border:1px solid #d8e4de;border-radius:10px;padding:10px;min-width:0}
.marketplace-offer h4{margin:0;font-size:15px}
.marketplace-shop{font-size:13px;overflow-wrap:anywhere}
.marketplace-figures{margin:6px 0 10px}
.marketplace-figures div{display:flex;flex-wrap:wrap;justify-content:space-between;column-gap:8px;font-size:14px}
.marketplace-figures dd{margin:0;font-variant-numeric:tabular-nums}
.marketplace-total{font-weight:750}
.marketplace-buy{display:flex;align-items:center;justify-content:center;min-height:44px;padding:6px;text-align:center;
  border:1px solid #447f6a;border-radius:8px;color:#104b3b;font-size:14px;font-weight:700;text-decoration:none}
.marketplace-buy:hover{background:#eef8f3;text-decoration:underline}
.marketplace-buy:focus-visible{outline:2px solid #154f40;outline-offset:2px}
.marketplace-footnote{font-size:13px}
@media(max-width:540px){.marketplace-prices{grid-template-columns:1fr}}
</style>"""


def timestamp(value):
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo is not None else None


def select(category, listings, client, *, include=PRODUCTS):
    products = []
    diagnostic = {}
    for product in include[category]:
        rakuten = defaultdict(list)
        yahoo = defaultdict(list)
        for row in listings:
            result = rakuten_offer(category, row, product)
            if result:
                count, offer = result
                rakuten[count].append(offer)
        if not rakuten:
            continue
        hits = client.search(jan=product.jan)
        seen = set()

        def collect(rows, *, additional=False):
            for hit in rows:
                code = hit.get("code")
                if not isinstance(code, str) or (additional and code in seen):
                    continue
                seen.add(code)
                result = yahoo_offer(category, hit, product, client.affiliate_link)
                if result:
                    count, offer = result
                    yahoo[count].append(offer)

        collect(hits)
        needs_total = any(any(offer.total is not None for offer in offers)
                          and not any(offer.total is not None for offer in yahoo.get(count, ()))
                          for count, offers in rakuten.items())
        if len(hits) == 50 and needs_total:
            # Small single packs can fill the first 50 results. A shipping
            # filter can expose additional sellers with comparable totals.
            collect(client.search(jan=product.jan, shipping="free"), additional=True)
        diagnostic[product.jan] = {"api_hits": len(seen), "rakuten_sizes": sorted(rakuten),
                                   "yahoo_sizes": sorted(yahoo)}
        for count in sorted(rakuten.keys() & yahoo.keys()):
            products.append((product, count, (cheapest_offer(rakuten[count]), cheapest_offer(yahoo[count]))))
    return products, diagnostic


def yen(amount):
    return f"¥{amount:,}"


def render_offer(category, offer, amount, scale, unit):
    marketplace = MARKETPLACES[offer.marketplace]
    shipping = yen(offer.shipping) if offer.shipping is not None else "要確認"
    total = yen(offer.total) if offer.total is not None else "要確認"
    unit_price = f"¥{offer.total * scale / amount:,.1f} / {unit}" if offer.total is not None else "—"
    return (
        f'<div class="marketplace-offer"><h4>{marketplace}</h4>'
        f'<p class="marketplace-shop">{html.escape(offer.shop)}</p>'
        '<dl class="marketplace-figures">'
        f'<div><dt>商品価格</dt><dd>{yen(offer.price)}</dd></div>'
        f'<div><dt>送料</dt><dd>{shipping}</dd></div>'
        f'<div class="marketplace-total"><dt>購入総額</dt><dd>{total}</dd></div>'
        f'<div><dt>送料込み単価</dt><dd>{unit_price}</dd></div></dl>'
        f'<a class="marketplace-buy" data-marketplace="{offer.marketplace}" data-category-id="{category}"'
        f' data-marketplace-item="{html.escape(offer.code)}" href="{html.escape(offer.url)}"'
        f' rel="sponsored nofollow noopener" target="_blank">{marketplace}で確認</a></div>'
    )


def render_totals(first, second):
    both = first.total is not None and second.total is not None
    blocks = []
    for offer, other in ((first, second), (second, first)):
        emphasis = ' class="marketplace-leading-total"' if both and offer.total < other.total else ""
        value = yen(offer.total) if offer.total is not None else "送料要確認"
        blocks.append(f'<div{emphasis}><dt>{MARKETPLACES[offer.marketplace]}</dt><dd>{value}</dd></div>')
    return '<dl class="marketplace-totals" aria-label="送料込みの購入総額">' + "".join(blocks) + '</dl>'


def render(category, groups, updated, rakuten_updated):
    entries = []
    japan = timezone(timedelta(hours=9))
    def shown(value):
        return value.astimezone(japan).strftime("%m/%d %H:%M")
    for product, count, (rakuten, yahoo) in groups:
        if rakuten.total is None or yahoo.total is None:
            note = "送料が未確定の候補があります。購入総額はショップで確認してください。"
        elif rakuten.total == yahoo.total:
            note = "掲載候補の購入総額は同じです。"
        else:
            name = "楽天市場" if rakuten.total < yahoo.total else "Yahoo!ショッピング"
            note = f"{name}が安い（差額 {yen(abs(rakuten.total - yahoo.total))}）"
        scale, factor, unit = price_unit(category, product)
        quantity = product.display_amount
        if product.unit in ("g", "ml"):
            packs = {"coffee": "袋", "water": "本"}.get(category, "個")
            quantity += f" × {count}{packs}"
        elif product.kitchen_rolls:
            quantity = f"× {count}パック"
        elif product.amount == 1:
            quantity = f"{count:,}{product.unit}"
        elif count > 1:
            quantity += f" × {count}パック"
        title = product.label if product.label_includes_quantity else f"{product.label} {quantity}"
        entries.append(
            f'<article class="marketplace-product" data-jan="{product.jan}" data-pack="{count}"'
            f' data-unit-amount="{product.amount}" data-unit="{product.unit}"'
            f' data-price-scale="{scale}" data-price-factor="{factor}" data-price-unit="{unit}">'
            f'<h3 id="{anchor(product.jan, count)}">{html.escape(title)}</h3>'
            f'<p><strong>{note}</strong></p>' + render_totals(rakuten, yahoo)
            + '<div class="marketplace-prices">' + "".join(render_offer(category, offer, product.amount * count * factor, scale, unit) for offer in (rakuten, yahoo))
            + '</div></article>'
        )
    return (
        f'<section {MARKER} aria-labelledby="marketplace-title">'
        '<h2 id="marketplace-title">楽天市場とYahoo!ショッピングを比較</h2>'
        '<p>容量・個数・商品規格が一致した掲載候補を比較しています。</p>'
        '<div class="marketplace-products">' + "".join(entries) + '</div>'
        '<p class="marketplace-footnote">税込。送料は取得時点の表示です。地域別送料・在庫は購入前にご確認ください。'
        'クーポン・ポイントは計算に含めていません。</p>'
        f'<p class="marketplace-footnote">価格取得（日本時間） 楽天市場 {shown(rakuten_updated)} ／ Yahoo!ショッピング {shown(updated)}。'
        '購入リンクは広告です。</p></section>'
    )


def navigation(entry_point, categories):
    links = []
    for category, name in categories:
        destination = (FRAGMENT if entry_point == "category"
                       else f"/daily-cost-jp/categories/{category}/{FRAGMENT}")
        label = "楽天市場とYahoo!ショッピングを比較する ↓" if entry_point == "category" else name
        links.append(
            f'<a class="marketplace-navigation-link" href="{html.escape(destination)}"'
            f' data-marketplace-entry="{entry_point}" data-category-id="{html.escape(category)}">'
            f'{html.escape(label)}</a>'
        )
    heading = '<h2>楽天市場とYahoo!ショッピングを比較</h2>' if entry_point != "category" else ""
    return (
        f'<nav {NAV_MARKER} aria-label="楽天市場とYahoo!ショッピングの比較">'
        + heading + '<div class="marketplace-navigation-links">' + "".join(links) + '</div></nav>'
    )


def add_credit(markup):
    if CREDIT in markup:
        return markup
    if markup.count("</footer>") != 1:
        raise ValueError("Marketplace credit footer changed")
    return markup.replace("</footer>", CREDIT + "\n</footer>", 1)


def insert_navigation(markup, entry_point, categories):
    if NAV_MARKER in markup:
        return markup
    if markup.count(MAIN) != 1 or markup.count("</head>") != 1:
        raise ValueError("marketplace navigation anchor changed")
    return (markup.replace(MAIN, MAIN + "\n" + navigation(entry_point, categories), 1)
            .replace("</head>", NAV_CSS + "\n</head>", 1))


def comparison_rows(category, listings, profiles, *, exact_refresh=refresh_exact):
    if category not in EXACT_RAKUTEN_CATEGORIES:
        return listings, [], None
    extra, status = exact_refresh(category, profiles)
    return extra, extra, status


def apply(site=Path("site"), *, client=None, now=None, include=PRODUCTS, exact_refresh=refresh_exact):
    now = now or datetime.now(timezone.utc)
    catalog = json.loads((site / "data.json").read_text(encoding="utf-8"))
    catalog_updated = timestamp(catalog.get("updated_at"))
    diagnostics = {
        category: {"rakuten_rows": len(data.get("items", [])), "yahoo_results": 0,
                   "pairs": 0, "comparable": 0, "status": "not_configured"}
        for category, data in catalog["categories"].items()
    }

    from rakuten_request import request_count
    initial_rakuten = request_count()
    consumption = {"additional_rakuten_discovery_requests": 0}

    def result(status):
        if "directory" not in consumption and (consumption.get("rakuten_limit")
                                                or consumption.get("discovery_status") == "baseline_api_error"):
            from marketplace_seeds import preserve_directory_history
            consumption["directory"] = preserve_directory_history(configured, now)
        consumption["marketplace_rakuten_requests"] = request_count() - initial_rakuten
        payload = {"status": status, "catalog_updated_at": catalog.get("updated_at"),
                   "categories": diagnostics, "api": consumption}
        (site / "marketplace-coverage.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        return payload

    configured = [category for category in include if category in diagnostics]
    if not catalog_updated or not timedelta(minutes=-5) <= now - catalog_updated <= timedelta(hours=24):
        for category in configured:
            diagnostics[category]["status"] = "rakuten_catalog_not_fresh"
        return result("rakuten_catalog_not_fresh")
    try:
        client = client or YahooShopping(os.getenv("YAHOO_APP_ID", ""), os.getenv("YAHOO_AFFILIATE_ID", ""))
    except YahooUnavailable as error:
        for category in configured:
            diagnostics[category]["status"] = str(error)
        return result(str(error))

    selected = {}
    errors = []
    rakuten_limit = None
    for category in configured:
        entry = diagnostics[category]
        if errors and errors[-1] in ("http_403", "http_429"):
            entry["status"] = "yahoo_request_limit"
            continue
        rows = catalog["categories"][category].get("items", [])
        if rakuten_limit and category in EXACT_RAKUTEN_CATEGORIES:
            rows, exact, exact_status = [], [], rakuten_limit
        else:
            rows, exact, exact_status = comparison_rows(category, rows, include[category], exact_refresh=exact_refresh)
            if exact_status in ("http_401", "http_403", "http_429"):
                rakuten_limit = exact_status
                consumption["rakuten_limit"] = exact_status
        if exact_status is not None:
            entry["rakuten_exact_status"] = exact_status
            entry["rakuten_exact_rows"] = len(exact)
        try:
            groups, candidates = select(category, rows, client, include=include)
        except YahooUnavailable as error:
            errors.append(str(error))
            entry["status"] = str(error)
            continue
        comparable = sum(all(offer.total is not None for offer in offers) for _, _, offers in groups)
        entry.update(pairs=len(groups), comparable=comparable, candidates=candidates,
                     yahoo_results=sum(row["api_hits"] for row in candidates.values()),
                     status="available" if comparable else "no_rakuten_match" if not candidates else "no_comparable_pair")
        if comparable:
            if exact:
                published_codes = {offers[0].code for _, _, offers in groups}
                entry["rakuten_exact_sources"] = [
                    {"item_code": row["item_code"], "price": row["price"], "name": row["name"],
                     "url_sha256": hashlib.sha256(row["url"].encode("utf-8")).hexdigest()}
                    for row in exact if row["item_code"] in published_codes
                ]
            selected[category] = groups

    input_path = site.parent / "marketplace-discovery-input.json"
    if input_path.is_file():
        snapshot = json.loads(input_path.read_text(encoding="utf-8"))
        if snapshot.get("updated_at") != catalog.get("updated_at"):
            raise ValueError("Discovery pool and catalog timestamps differ")
        if not errors:
            from marketplace_seeds import extend_current
            pool = snapshot["categories"]
            categories = {key: include[key] for key in configured}
            keyword_hits = {}
            if not rakuten_limit and all(os.getenv(key) for key in ("RAKUTEN_APPLICATION_ID", "RAKUTEN_ACCESS_KEY", "RAKUTEN_AFFILIATE_ID")):
                initial_requests = request_count()
                consumption["directory"], keyword_hits = extend_current(pool, categories, client)
                consumption["additional_rakuten_discovery_requests"] = request_count() - initial_requests
            before = client.requests
            extra_groups, reports = discover(pool, categories, client, keyword_hits=keyword_hits)
            for category, report in reports.items():
                entry = diagnostics[category]
                entry["discovery"] = report
                additions = extra_groups.get(category, [])
                if additions:
                    selected.setdefault(category, []).extend(additions)
                    entry["pairs"] += len(additions)
                    entry["comparable"] += len(additions)
                    entry["status"] = "available"
                entry["yahoo_results"] += report["hits"]
            consumption["discovery_yahoo_requests"] = client.requests - before
        else:
            consumption["discovery_status"] = "baseline_api_error"
    consumption.update(yahoo_requests=client.requests, yahoo_cache_hits=client.cache_hits)
    sections = {category: render(category, groups, now, catalog_updated)
                for category, groups in selected.items()}

    available = [(category, catalog["categories"][category]["name"]) for category in sections]
    pages = {}
    for category, section in sections.items():
        page = site / "categories" / category / "index.html"
        markup = page.read_text(encoding="utf-8")
        if MARKER in markup:
            continue
        # Use the purchase summary as an insertion point and place the required
        # Yahoo credit at the bottom of each page that uses Yahoo data.
        if markup.count('</footer>') != 1 or markup.count('</head>') != 1:
            raise ValueError("marketplace page structure changed")
        anchor = ANCHOR if ANCHOR in markup else f'<section class="category-section" id="{category}">'
        if markup.count(anchor) != 1:
            raise ValueError("marketplace section anchor changed")
        markup = markup.replace(anchor, section + "\n" + anchor, 1)
        markup = add_credit(markup)
        markup = markup.replace('</head>', CSS + '\n</head>', 1)
        pages[page] = insert_navigation(markup, "category", [(category, "")])
    if available:
        for path, entry_point in (("index.html", "home"), ("categories/index.html", "directory")):
            page = site / path
            pages[page] = insert_navigation(page.read_text(encoding="utf-8"), entry_point, available)
    finder = site / "products/index.html"
    if selected and finder.is_file():
        pages[finder] = add_credit(add_finder(finder.read_text(encoding="utf-8"), selected))
    for page, markup in pages.items():
        temp = page.with_suffix('.tmp')
        temp.write_text(markup, encoding="utf-8")
        temp.replace(page)
    return result("rendered" if sections else errors[0] if errors else "no_comparable_pair")


if __name__ == "__main__":
    print("Marketplace comparison:", json.dumps(apply(), ensure_ascii=False, sort_keys=True))
