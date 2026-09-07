import json
import re
from pathlib import Path

PAGES = [
    Path("site/index.html"),
    Path("site/products/index.html"),
]

FAQS = [
    (
        "「送料込み最安値」とは？",
        "楽天市場で送料込み／送料無料と確認でき、商品名・ブランド・JANコード・容量や個数などから同一商品と判断できた購入候補のうち、取得時点で最も安い価格です。",
    ),
    (
        "価格を取得できない商品があるのはなぜ？",
        "似た商品や容量違いを誤って最安値として出さないためです。同一商品だと十分に確認できない場合は、数字を無理に表示せず「楽天で価格を確認」と表示します。",
    ),
    (
        "検索結果の画像が楽天の画像に切り替わるのはなぜ？",
        "送料込み価格を確認できた商品では、実際にその価格でリンクする楽天市場の購入候補画像を表示しています。商品名だけでなく画像でも購入対象を確認しやすくするためです。",
    ),
    (
        "価格やランキングはいつ更新される？",
        "商品名検索は検索した時点で楽天へ問い合わせます。日用品の単価ランキングと楽天総合ランキングは自動更新され、画面に表示される更新時刻は取得時点の目安です。",
    ),
    (
        "クーポンや楽天ポイントは価格に含まれる？",
        "含めていません。クーポン、ポイント還元、会員条件、配送地域などで最終支払額が変わることがあるため、購入前に楽天市場の画面で最終金額を確認してください。",
    ),
    (
        "このサイトは楽天アフィリエイトを使っている？",
        "はい。楽天市場への一部リンクは楽天アフィリエイトを利用しています。リンク経由で購入されると運営者に成果報酬が発生する場合がありますが、利用者の販売価格がそのために上がることはありません。",
    ),
]

STYLE = '''<style id="trust-faq-style">
#trust-faq{margin:30px 0 18px;padding:18px;border:1px solid #e7e1dc;border-radius:20px;background:#fff}
#trust-faq .trust-faq-kicker{font-size:11px;font-weight:900;color:#b3261e;letter-spacing:.03em}
#trust-faq h2{font-size:20px;line-height:1.35;margin:3px 0 6px;color:#252525}
#trust-faq .trust-faq-lead{font-size:11px;line-height:1.7;color:#6b7280;margin:0 0 12px}
#trust-faq details{border-top:1px solid #eee7e2;padding:0}
#trust-faq details:last-of-type{border-bottom:1px solid #eee7e2}
#trust-faq summary{list-style:none;cursor:pointer;padding:13px 22px 13px 0;font-size:13px;font-weight:850;line-height:1.55;position:relative;color:#252525}
#trust-faq summary::-webkit-details-marker{display:none}
#trust-faq summary::after{content:'＋';position:absolute;right:2px;top:12px;color:#b3261e;font-size:17px;font-weight:700}
#trust-faq details[open] summary::after{content:'−'}
#trust-faq .trust-faq-answer{font-size:11px;line-height:1.8;color:#5f6368;padding:0 0 13px;margin:0}
#trust-faq .trust-faq-note{font-size:10px;line-height:1.7;color:#7a6f69;margin:12px 0 0}
@media(max-width:520px){#trust-faq{margin-left:0;margin-right:0;padding:15px;border-radius:17px}#trust-faq h2{font-size:18px}}
</style>'''


def block() -> str:
    details = []
    for question, answer in FAQS:
        details.append(
            f'<details><summary>{question}</summary><p class="trust-faq-answer">{answer}</p></details>'
        )
    return f'''<section id="trust-faq" aria-labelledby="trust-faq-title">
  <div class="trust-faq-kicker">価格表示について</div>
  <h2 id="trust-faq-title">このサイトの価格の考え方</h2>
  <p class="trust-faq-lead">安く見せることより、別商品や送料別価格を誤って最安値として出さないことを優先しています。</p>
  {''.join(details)}
  <p class="trust-faq-note">価格・在庫・送料条件は変動します。最終的な購入条件は楽天市場の商品ページで必ず確認してください。</p>
</section>'''


def schema() -> str:
    payload = {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {
                "@type": "Question",
                "name": question,
                "acceptedAnswer": {"@type": "Answer", "text": answer},
            }
            for question, answer in FAQS
        ],
    }
    return '<script id="trust-faq-schema" type="application/ld+json">' + json.dumps(payload, ensure_ascii=False) + '</script>'


def inject(path: Path) -> bool:
    if not path.exists():
        return False
    text = path.read_text(encoding="utf-8")
    text = re.sub(r'<style id="trust-faq-style">.*?</style>', '', text, flags=re.DOTALL)
    text = re.sub(r'<section id="trust-faq".*?</section>', '', text, flags=re.DOTALL)
    text = re.sub(r'<script id="trust-faq-schema".*?</script>', '', text, flags=re.DOTALL)

    if '</head>' in text:
        text = text.replace('</head>', STYLE + '\n' + schema() + '\n</head>', 1)

    faq = block()
    if path.name == 'index.html' and path.parent.name == 'products':
        marker = '<section id="product-ranking-cta"'
        pos = text.find(marker)
        if pos >= 0:
            text = text[:pos] + faq + '\n' + text[pos:]
        elif '</main>' in text:
            text = text.replace('</main>', faq + '\n</main>', 1)
        else:
            text = text.replace('</body>', faq + '\n</body>', 1)
    elif '</main>' in text:
        text = text.replace('</main>', faq + '\n</main>', 1)
    else:
        text = text.replace('</body>', faq + '\n</body>', 1)

    path.write_text(text, encoding="utf-8")
    return True


def main():
    changed = sum(1 for path in PAGES if inject(path))
    print(f"Added trust FAQ to {changed} pages")


if __name__ == '__main__':
    main()
