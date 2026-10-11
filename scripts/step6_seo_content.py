"""Source-owned fixed buying help; policy changes require a human-reviewed PR.

No report text, search query, HTML or product value becomes executable copy.
Default policy is inert. Existing ranking, metadata and tracking stay intact.
"""
import html
import json
from pathlib import Path

TARGET = 'scripts/step6_seo_policy.json'
VERSION = 'comparison-help-v1'
REGISTRY = {
    'laundry': ('洗濯洗剤', 'kg', 'laundry-detergent-cost-per-use',
                '容量あたりの単価と、洗濯1回あたりの費用は同じですか？',
                '同じではありません。商品の使用量表示も確認してください。使用量が不明な商品の1回あたりの費用を推測していません。'),
    'tissue': ('ティッシュ', '箱', 'tissue-price-per-box',
               '箱数が同じなら、ティッシュの量も同じですか？',
               '同じとは限りません。1箱あたりの組数・枚数や箱の大きさも確認してください。5箱入りを12パック購入する場合は合計60箱です。'),
    'toilet-paper': ('トイレットペーパー', 'ロール', 'toilet-paper-price-per-meter',
                     'ロール数が同じなら、使える長さも同じですか？',
                     '同じとは限りません。1ロールの長さとシングル・ダブルの規格を確認してください。規格が異なる商品を同一商品として扱っていません。'),
}
MARKER = '<!-- STEP6 comparison-help-v1 -->'


def policy(text):
    obj = json.loads(text)
    if (not isinstance(obj, dict) or set(obj) != {'version', 'pages'} or
            obj['version'] != VERSION or not isinstance(obj['pages'], dict) or
            set(obj['pages']) != set(REGISTRY) or
            any(type(v) is not bool for v in obj['pages'].values())):
        raise ValueError('Invalid fixed SEO policy')
    return obj


def recipe(cid):
    if cid not in REGISTRY:
        raise ValueError('Unknown fixed page')
    return VERSION + ':' + cid


def repair(text, name):
    cid = next((c for c in REGISTRY if recipe(c) == name), None)
    if cid is None:
        return None
    try:
        obj = policy(text)
    except (ValueError, TypeError):
        return None
    if obj['pages'][cid]:
        return None
    obj['pages'][cid] = True
    return json.dumps(obj, ensure_ascii=False, indent=2) + '\n'


def markup(cid):
    name, unit, guide, question, answer = REGISTRY[cid]
    esc = html.escape
    return MARKER + (
        '<section id="step6-comparison-help" class="category-seo-faq" aria-labelledby="step6-help-title">'
        f'<h2 id="step6-help-title">{esc(name)}の説明を読んだあとの比較</h2>'
        '<details><summary>買う量と比較条件を決めたら、どこで確認できますか？</summary>'
        '<p>使い切れる量と収納場所を確認し、同じ規格の単価と送料込み支払総額を比べてください。'
        f'<a href="#{cid}">このページの単価ランキングに戻る</a>ことができます。'
        '価格・在庫・配送条件は購入前に楽天の商品ページで確認してください。</p></details>'
        f'<p><a href="/daily-cost-jp/guides/{guide}/">比較単位と選び方の説明</a> · '
        '<a href="/daily-cost-jp/products/">いつもの商品を検索</a> · '
        '<a href="/daily-cost-jp/categories/">関連カテゴリを探す</a></p></section>')


def apply(site=Path('site'), config=None):
    from bs4 import BeautifulSoup
    obj = policy(Path(TARGET).read_text()) if config is None else policy(json.dumps(config))
    changed = []
    for cid, enabled in obj['pages'].items():
        if not enabled:
            continue
        path = site / 'categories' / cid / 'index.html'
        text = path.read_text()
        if MARKER in text:
            continue
        soup = BeautifulSoup(text, 'html.parser')
        canonical = soup.select('link[rel=canonical]')
        expected = f'https://stusaurus.github.io/daily-cost-jp/categories/{cid}/'
        if (len(canonical) != 1 or canonical[0].get('href') != expected or
                len(soup.select('main')) != 1 or text.count('</main>') != 1 or
                len(soup.select('h1')) != 1):
            raise ValueError('Unexpected fixed category template')
        path.write_text(text.replace('</main>', markup(cid) + '</main>', 1))
        changed.append(cid)
    return changed


if __name__ == '__main__':
    print('STEP6 fixed help rendered:', apply())
