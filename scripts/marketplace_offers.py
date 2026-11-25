"""Exact package matching and comparable offer selection across marketplaces."""
from dataclasses import dataclass
from decimal import Decimal
import re
from urllib.parse import parse_qs

from product_quality import category_rejection
from sale_quantity import normalize, parse_sale_quantity
from yahoo_shopping import safe_url

PACK_COUNT = re.compile(r"(?<![\d.])(\d+)\s*(?:個|袋|本|パック|セット|箱|ケース)")
MULTIPLIER = re.compile(r"x\s*(\d+)(?![\d.])", re.I)
CAPACITY = re.compile(r"(?<![\w.])([\d]+(?:\.\d+)?)\s*(kg|ml|g|l)(?=x\s*\d|[^a-z]|$)", re.ASCII)
AMBIGUOUS = re.compile(
    r"選べ|組み合わせ|おまけ|増量品|お試し|サンプル|アソート|混合|"
    r"(?:新旧|旧品|旧パッケージ)|(?:本体|ボトル)(?:付き|付|セット)|"
    r"(?:個|袋|本|パック)\s*[+＋＆&]|[+＋＆&]\s*\d+\s*(?:個|袋|本|パック)"
)
SHIPPING_CONDITIONS = re.compile(
    r"条件付き送料無料|送料無料ライン|送料別(?:途)?|送料有料|配送不可|"
    r"(?:北海道|沖縄|離島|一部地域).{0,24}(?:送料|別途|対象外|除く)|"
    r"(?:送料|配送|発送).{0,24}(?:北海道|沖縄|離島|一部地域)|"
    r"[\d,.]+円(?:以上|から).{0,20}(?:送料無料|送料0円)|"
    r"(?:送料無料|送料0円).{0,20}[\d,.]+円(?:以上|から)"
)


def valid_jan(code):
    return bool(isinstance(code, str) and re.fullmatch(r"[0-9]{8}|[0-9]{13}", code)
                and sum(int(digit) * (3 if i % 2 else 1)
                        for i, digit in enumerate(reversed(code))) % 10 == 0)


@dataclass(frozen=True)
class Product:
    jan: str
    label: str
    amount: int
    unit: str
    required: tuple[str, ...]
    excluded: str

    @property
    def display_amount(self):
        return f"{self.amount:,}{self.unit}"


@dataclass(frozen=True)
class Offer:
    marketplace: str
    code: str
    shop: str
    price: int
    shipping: int | None
    url: str

    @property
    def total(self):
        return self.price + self.shipping if self.shipping is not None else None


def package_quantity(category, title, product):
    """Require independent title evidence for variant, per-unit size and pack."""
    text = normalize(title).lower()
    if (not valid_jan(product.jan) or AMBIGUOUS.search(text)
            or category_rejection(category, text)
            or any(not re.search(pattern, text) for pattern in product.required)
            or re.search(product.excluded, text)):
        return None
    sizes = set()
    dimension = {"kg": "g", "g": "g", "l": "ml", "ml": "ml"}
    for amount, unit in CAPACITY.findall(text):
        sizes.add((Decimal(amount) * (1000 if unit in ("kg", "l") else 1), dimension[unit]))
    if sizes != {(product.amount, product.unit)}:
        return None
    # For example, a single retail JAN may be shared by each seller's 3-pack,
    # 6-pack or case. Never use the JAN itself as evidence for the sale count.
    counts = {int(count) for count in PACK_COUNT.findall(text)}
    multipliers = MULTIPLIER.findall(text)
    if len(multipliers) > 1 or re.search(r"\d+\s*(?:箱|ケース|個\s*x|袋\s*x|本\s*x|パック\s*x)", text):
        return None
    if multipliers:
        counts.add(int(multipliers[0]))
    if len(counts) > 1 or re.search(r"\d+\s*(?:本|袋|個)\s*(?:で|を)\s*1セット", text):
        return None
    if not counts and re.search(r"セット|まとめ買い|ケース|詰め合わせ|複数", text):
        return None
    quantity = counts.pop() if counts else 1
    return quantity if 1 <= quantity <= 24 else None


def rakuten_product_link(value, code):
    url = safe_url(value)
    match = re.fullmatch(r"([\w-]+):([0-9]+)", str(code or ""), re.ASCII)
    if not url or not match or url.scheme != "https" or url.hostname != "hb.afl.rakuten.co.jp":
        return False
    if not url.path.startswith("/hgc/"):
        return False
    params = parse_qs(url.query)
    pc = safe_url(first(params, "pc"))
    mobile = safe_url(first(params, "m"))
    return bool(pc and mobile and pc.scheme == "https" and mobile.scheme in ("http", "https")
                and pc.hostname == "item.rakuten.co.jp" and mobile.hostname == "m.rakuten.co.jp"
                and re.fullmatch(rf"/{re.escape(match[1])}/[\w.-]+/?", pc.path, re.ASCII)
                and mobile.path == f"/{match[1]}/i/{match[2]}/")


def first(params, name):
    values = params.get(name, ())
    return values[0] if len(values) == 1 else None


def clean_shop(name):
    return name.strip() if isinstance(name, str) and 0 < len(name.strip()) <= 90 else None


def known_shipping(text):
    return not SHIPPING_CONDITIONS.search(normalize(text))


def rakuten_offer(category, row, product):
    name = row.get("name", "")
    codes = {code for code in re.findall(r"(?<!\d)(?:\d{13}|\d{8})(?!\d)", normalize(name))
             if valid_jan(code)}
    if row.get("category_id") != category or row.get("quality_version") != 1 or codes != {product.jan}:
        return None
    count = package_quantity(category, name, product)
    quantity = parse_sale_quantity(row.get("sale_quantity_label", ""))
    price, link, code = row.get("price"), row.get("url"), row.get("item_code")
    shop = clean_shop(row.get("shop"))
    if (count is None or not quantity or quantity.get("base_amount") != product.amount * count
            or quantity.get("kind") != ("weight" if product.unit == "g" else "volume")
            or type(price) is not int or price <= 0 or not shop or not rakuten_product_link(link, code)):
        return None
    shipping = 0 if row.get("postage") == "送料込み" and known_shipping(name) else None
    return count, Offer("rakuten", code, shop, price, shipping, link)


def yahoo_offer(category, hit, product, affiliate_link):
    name = hit.get("name", "")
    if hit.get("janCode") != product.jan or hit.get("inStock") is not True or hit.get("condition") != "new":
        return None
    other_jans = {code for code in re.findall(r"(?<!\d)\d{13}(?!\d)", normalize(name)) if valid_jan(code)}
    if other_jans - {product.jan}:
        return None
    count = package_quantity(category, name, product)
    price, label = hit.get("price"), hit.get("priceLabel")
    seller, shipping_data = hit.get("seller"), hit.get("shipping")
    shop = clean_shop(seller.get("name")) if isinstance(seller, dict) else None
    link = affiliate_link(hit)
    if (count is None or type(price) is not int or price <= 0 or not isinstance(label, dict)
            or label.get("taxable") is not True or not shop or not link):
        return None
    terms = " ".join(str(hit.get(key) or "") for key in ("name", "headLine", "description"))
    shipping = 0 if isinstance(shipping_data, dict) and shipping_data.get("code") == 2 and known_shipping(terms) else None
    return count, Offer("yahoo", hit["code"], shop, price, shipping, link)


def cheapest_offer(offers):
    # A conditional price can never outrank a confirmed checkout total.
    return min(offers, key=lambda offer: (offer.total is None,
                                         offer.total if offer.total is not None else offer.price,
                                         offer.code))
