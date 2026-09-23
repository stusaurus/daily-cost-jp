"""Daily-goods examples, independent of general-market trends.

Reviewed against GSC queries through 2026-09-22: Attack ZERO, tissue and toilet
paper have purchase-intent impressions. Other brands are relevant examples,
not popularity claims. Historical internal searches contain operator tests.
"""
import html
import re
from pathlib import Path
from product_quality import category_is_suitable

PRODUCTS = Path('site/products/index.html')
HOME = Path('site/index.html')
# label, complete search query, category (never arbitrary trending brands).
SUGGESTIONS = [
    ('アタックZERO', 'アタックZERO 洗濯洗剤', 'laundry'),
    ('スコッティ ティッシュ', 'スコッティ ティッシュペーパー', 'tissue'),
    ('トイレットペーパー', 'トイレットペーパー', 'toilet-paper'),
    ('アリエール', 'アリエール 洗濯洗剤', 'laundry'),
    ('さらさ', 'さらさ 洗濯洗剤', 'laundry'),
    ('ワイドハイター', 'ワイドハイター 衣料用漂白剤', 'laundry-bleach'),
    ('キュキュット', 'キュキュット 食器用洗剤', 'dish'),
    ('キレイキレイ', 'キレイキレイ ハンドソープ', 'hand-soap'),
]


def checked_suggestions():
    return [(label, query, category) for label, query, category in SUGGESTIONS
            if category_is_suitable(category, query)]


def replace_product_chips(markup):
    buttons = ''.join(
        f'<button class="chip" data-q="{html.escape(query, quote=True)}" '
        f'data-category="{category}" data-conversion-source="product_search">{html.escape(label)}</button>'
        for label, query, category in checked_suggestions())
    block = '<div class="examples" aria-label="日用品の商品名から検索">' + buttons + '</div>'
    markup = re.sub(r'<div class="examples"[^>]*>.*?</div>', block, markup, count=1, flags=re.S)
    markup = re.sub(r'placeholder="(?:例：おしりセレブ / アリエール / JANコード|今人気の商品名・ブランド・JANコード)"',
                    'placeholder="例：アタックZERO 2100g / 商品名・JANコード"', markup, count=1)
    return markup


def main():
    if not PRODUCTS.exists():
        raise SystemExit('Product page unavailable')
    PRODUCTS.write_text(replace_product_chips(PRODUCTS.read_text(encoding='utf-8')), encoding='utf-8')
    if HOME.exists():
        markup = HOME.read_text(encoding='utf-8').replace(
            '「おしりセレブ」「アリエール」など、欲しい製品そのものを選んで楽天価格ナビの購入可能な最低価格を確認できます。',
            '欲しい商品名やブランド名を入れて、楽天で確認できる送料込み価格を探せます。')
        HOME.write_text(markup, encoding='utf-8')
    print('Daily-goods search examples: ' + ', '.join(x[0] for x in checked_suggestions()))


if __name__ == '__main__':
    main()
