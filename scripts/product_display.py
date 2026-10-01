"""Conservative display-only cleanup. Never use this for product validation."""
import re
import unicodedata

PROMO = re.compile(
    r'(?:最大\s*)?[\d,]+\s*(?:円|%)\s*(?:OFF|オフ|引き?)(?:\s*クーポン)?'
    r'|(?:先着(?:限定)?)?クーポンで(?:最安)?(?:1箱)?[\d,]+円(?:[~〜～])?'
    r'|クーポン利用で(?:最安)?[\d,]+円(?:[~〜～])?'
    r'|(?:ポイント\s*|P\s*)(?:最大\s*)?\d+\s*倍'
    r'|(?:最大\s*)?\d+\s*%\s*ポイントバック|当選確率\d+分の\d+'
    r'|エントリーで全品ポイント\d+倍'
    r'|くらしにプラス'
    r'|\d+\s*時間限定|本日(?:限定|限り)|マラソン(?:中|期間中|限定)'
    r'|(?:\d{4}年(?:間)?)?(?:楽天)?ランキング\d+位(?:受賞)?'
    r'|楽天\d+位|高評価(?:人気商品)?|まとめ買いお得|365日最短当日出荷'
    r'|送料無料|送料込み|クーポン対象|SALE|セール中?', re.I)
DATE = re.compile(
    r'(?:\d{1,2}/\d{1,2}|\d{1,2}月\d{1,2}日)'
    r'(?:から\d{1,2}日)?(?:限定|限り)?')
LEADING_LABEL = re.compile(r'^\s*(?:【([^】]+)】|\[([^\]]+)\]|＼([^／]+)／)\s*')
BARE_PROMO = re.compile(
    r'^\s*(?:高評価(?:人気商品)?|(?:\d{4}年(?:間)?)?(?:楽天)?ランキング\d+位(?:受賞)?'
    r'|レビュー記入で[\d,]+円クーポンプレゼント)'
    r'[\s★☆彡!！+＋・♪／/、。~〜～:：%％-]*', re.I)
BARE_DATE_TIME = re.compile(
    r'^\s*(?:\d{1,2}/\d{1,2}|\d{1,2}月\d{1,2}日)(?:限定|限り)?'
    r'(?:\s*\d{1,2}:\d{2}(?:迄|まで)?)?\s*')


def promotion_only(label):
    text = unicodedata.normalize('NFKC', label)
    if not (PROMO.search(text) or re.search(r'(?:\d{1,2}/\d{1,2}|\d{1,2}月\d{1,2}日)限定', text)):
        return False
    rest = DATE.sub('', PROMO.sub('', text))
    rest = re.sub(r'(?:[~〜～]\s*)?\d{1,2}日(?=\d{1,2}:\d{2})|\d{1,2}:\d{2}(?:迄|まで)?', '', rest)
    # Any remaining word, number, brand, capacity, count or type keeps the label.
    return not re.sub(r'[\s★☆彡!！+＋・＼\\／/、。~〜～:：%％-]', '', rest)


def clean_display_name(name):
    original = str(name or '').strip()
    text = original
    removed_promotion = False
    while True:
        before = text
        if match := LEADING_LABEL.match(text):
            if promotion_only(next(g for g in match.groups() if g is not None)):
                remainder = text[match.end():].lstrip()
                if remainder:
                    text = remainder
                    removed_promotion = True
                    continue
        if match := BARE_PROMO.match(text):
            remainder = text[match.end():].lstrip()
            if remainder:
                text = remainder
                removed_promotion = True
                continue
        if removed_promotion and (match := BARE_DATE_TIME.match(text)):
            remainder = text[match.end():].lstrip()
            if remainder:
                text = remainder
                continue
        if text == before:
            break
    # Bare, exact promotion prefixes only. Keep unknown/mixed wording intact.
    text = re.sub(r'^(?:(?:送料無料|送料込み|本日限定|本日限り|マラソン中)\s*[!！★☆＋+・]*\s*)+', '', text)
    return re.sub(r'\s+', ' ', text).strip() or original
