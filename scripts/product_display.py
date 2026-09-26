"""Conservative display-only cleanup. Never use this for product validation."""
import re
import unicodedata

PROMO = re.compile(
    r'(?:最大\s*)?[\d,]+\s*(?:円|%)\s*(?:OFF|オフ)(?:\s*クーポン)?'
    r'|(?:ポイント\s*|P\s*)(?:最大\s*)?\d+\s*倍'
    r'|\d+\s*時間限定|本日(?:限定|限り)|マラソン(?:中|期間中|限定)'
    r'|送料無料|送料込み|クーポン対象|SALE|セール中?', re.I)
DATE = re.compile(r'(?:\d{1,2}/\d{1,2}|\d{1,2}月\d{1,2}日)(?:限定|限り)?')
LEADING_LABEL = re.compile(r'^\s*(?:【([^】]+)】|\[([^\]]+)\]|＼([^／]+)／)\s*')


def promotion_only(label):
    text = unicodedata.normalize('NFKC', label)
    if not (PROMO.search(text) or re.search(r'(?:\d{1,2}/\d{1,2}|\d{1,2}月\d{1,2}日)限定', text)):
        return False
    rest = DATE.sub('', PROMO.sub('', text))
    rest = re.sub(r'(?:[~〜～]\s*)?\d{1,2}日(?=\d{1,2}:\d{2})|\d{1,2}:\d{2}(?:迄|まで)?', '', rest)
    # Any remaining word, number, brand, capacity, count or type keeps the label.
    return not re.sub(r'[\s★☆彡!！+＋・／/、。~〜～:：%％-]', '', rest)


def clean_display_name(name):
    original = str(name or '').strip()
    text = original
    while match := LEADING_LABEL.match(text):
        if not promotion_only(next(g for g in match.groups() if g is not None)):
            break
        remainder = text[match.end():].lstrip()
        if not remainder:
            break
        text = remainder
    # Bare, exact promotion prefixes only. Keep unknown/mixed wording intact.
    text = re.sub(r'^(?:(?:送料無料|送料込み|本日限定|本日限り|マラソン中)\s*[!！★☆＋+・]*\s*)+', '', text)
    return re.sub(r'\s+', ' ', text).strip() or original
