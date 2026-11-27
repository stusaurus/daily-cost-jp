"""Discover retail packages from this build's validated Rakuten acquisition pool."""
from collections import Counter, defaultdict
from dataclasses import replace
from decimal import Decimal
import hashlib
import re
from urllib.parse import parse_qs

from comparison_units import toilet_ply_length
from marketplace_offers import (AMBIGUOUS, CAPACITY, CATALOG_UNITS, Product,
                               count_title, explicit_jans, first, known_shipping, package_quantity,
                               rakuten_offer, rakuten_product_link, valid_jan, yahoo_offer)
from product_display import clean_display_name
from product_quality import category_rejection, kitchen_roll_package
from sale_quantity import normalize, parse_sale_quantity
from yahoo_shopping import YahooUnavailable, safe_url

# One request per distinct JAN. The established profiles always run first.
PER_CATEGORY = 24
BUILD_BUDGET = 300
GTIN = re.compile(r"(?<!\d)\d{13}(?!\d)")
CAPTION_JAN = re.compile(r"(?:jan(?:コード|番号)?|バーコード)\s*[】):：/／]?\s*[:：]?\s*(\d{13})(?!\d)", re.I)
# Retailer specifications sometimes separate the JAN label and value with table cells.
SPEC_TAG = re.compile(r"</?(?:td|th|tr|dl|dt|dd|br|span)\b[^>]*>", re.I)
UNSAFE = re.compile(r"選択|選んで|いずれか|旧(?:製品|型|商品|モデル|仕様|処方|デザイン|タイプ)|リニューアル|新旧|訳あり|福袋|ランダム|おまけ|景品|プレゼント付|種類指定不可|パッケージ.{0,8}(?:異なる|変更)|定期購入|定期便")
PACK = re.compile(r"(?<![\d.])\d+\s*(?:ロール|パック|ケース|セット|枚|個|本|箱|袋)(?:入り?)?")
DECORATION = re.compile(r"送料無料|送料込み|まとめ買い|ケース販売|ケース売り|公式ショップ|公式ストア|税込")
# Strip standalone sales language after checking quantities, never variant adjectives.
PROMOTIONAL = re.compile(r"(?:単品販売|セット販売|販売セット|お買い得品|お買い得|"
                         r"まとめて購入|国内正規流通品|日用消耗品|日用品雑貨|セット$)")

UNKNOWN_PACK = re.compile(r"(?:[2-9]|[1-9]\d+)\s*(?:ヶ|ケ|箇|コ)\s*(?:入り?|組|セット)|\d+\s*(?:点|組セット|コ組|缶|束|箱組|種類|個口)|[+＋]|(?:単品|セット)から|(?:色|柄|香り)指定不可")
# Only seller boilerplate may surround a complete official directory name.
NEUTRAL = re.compile(r"ケース販売|ケース売り|まとめ買い|セット販売|セット|パック販売|大容量|特大サイズ|"
                     r"日用品|国内正規品|日本製|送料無料|送料込み|税込|単品販売|単品|日用雑貨")
REFILL = re.compile(r"(?:詰|つ)め?(?:替|換|か)え?(?:用)?|(?:レフィル|リフィル)")
# Generic category labels may accompany an intact directory product name.
# Keep material, format, scent, size, model and formula words in both seller titles.
CATEGORY_LABELS = {
    "dish": "食器用洗剤", "laundry": "衣料用洗剤", "softener": "柔軟剤",
    "shampoo": "シャンプー", "conditioner": "コンディショナー", "hand-soap": "ハンドソープ",
    "bath-cleaner": "浴室用洗剤", "toilet-cleaner": "トイレ用洗剤", "toothbrush": "歯ブラシ",
    "mouthwash": "マウスウォッシュ", "toothpaste": "歯磨き粉", "body-soap": "ボディソープ",
}

def product_path(row):
    url = safe_url(row.get("url"))
    target = safe_url(first(parse_qs(url.query), "pc")) if url else None
    return target.path.rstrip("/") if target and target.hostname == "item.rakuten.co.jp" else ""


def source_evidence(raw, row):
    """Bind a current, purchasable offer to one uncontradicted retail GTIN."""
    title, caption = raw.get("itemName"), raw.get("itemCaption")
    if (raw.get("availability") != 1 or raw.get("postageFlag") != 0
            or not isinstance(caption, str) or not caption.strip() or not isinstance(title, str)
            or not known_shipping(title + " " + caption) or UNSAFE.search(normalize(title + " " + caption))
            or not rakuten_product_link(row.get("url"), row.get("item_code"))):
        return None
    title, caption = normalize(title), normalize(caption)
    path = product_path(row)
    labelled = set(CAPTION_JAN.findall(SPEC_TAG.sub(" ", caption)))
    path_codes = set(GTIN.findall(path))
    codes = set(GTIN.findall(title)) | path_codes | labelled
    # Arbitrary internal IDs in prose cannot supply the identity.
    if len(codes) != 1 or not all(valid_jan(code) and len(set(code)) > 1 for code in codes):
        return None
    jan = next(iter(codes))
    if any(code != jan and valid_jan(code) for code in GTIN.findall(caption)):
        return None
    return {"jan": jan, "basis": "title" if jan in title else "product_path" if jan in path_codes else "caption_jan"}


def package_profile(category, row):
    name, jan = row["name"], row["jan"]
    text = normalize(name).lower()
    if UNSAFE.search(text) or UNKNOWN_PACK.search(text) or AMBIGUOUS.search(text) or category_rejection(category, text):
        return None
    tissue_pairs = roll_length = kitchen_rolls = None
    if category == "tissue":
        pairs = set(re.findall(r"(\d+)\s*組", text))
        if len(pairs) != 1:
            return None
        tissue_pairs = int(pairs.pop())
        if tissue_pairs <= 0:
            return None
        text = re.sub(r"\d+\s*(?:組(?:\s*/\s*箱)?|枚)", "", text)
    elif category == "toilet-paper":
        dimension = toilet_ply_length(row)
        if not dimension or not dimension[1].is_integer():
            return None
        roll_length = int(dimension[1])
    if row["metric"] in ("100ml", "100g", "1L"):
        sizes = {(Decimal(n) * (1000 if u in ("kg", "l") else 1),
                  "g" if u in ("g", "kg") else "ml") for n, u in CAPACITY.findall(text)}
        if len(sizes) != 1:
            return None
        amount, unit = sizes.pop()
        if amount != int(amount):
            return None
    elif category == "kitchen-paper" and (dimensions := kitchen_roll_package(name)):
        per_roll, kitchen_rolls, _ = dimensions
        amount, unit = per_roll * kitchen_rolls, "枚"
    else:
        quantity = parse_sale_quantity(count_title(category, text))
        if not quantity or quantity["kind"] != "count":
            return None
        unit = quantity["count_unit"]
        amount = quantity["total_count"] // (quantity.get("outer_count") or 1)
        if CATALOG_UNITS.get(unit) != row["metric"]:
            return None
    if amount <= 0:
        return None
    return Product(jan, clean_display_name(name), int(amount), unit, (), "",
                   roll_length_m=roll_length, tissue_pairs=tissue_pairs, kitchen_rolls=kitchen_rolls,
                   rakuten_evidence=((row["item_code"], product_path(row)),))


def identity_text(name, jan, category=None):
    # Retain all product words, formula, size, fragrance, model and manufacturer.
    # Remove only presentation and quantities which are checked independently.
    text = normalize(clean_display_name(name)).lower().replace(jan, "")
    text = REFILL.sub("詰替", text)
    if category == "toothbrush":
        text = re.sub(r"歯ブラシ|ハブラシ|はぶらし", "ハブラシ", text)
    if category == "tissue":
        text = re.sub(r"ティシュー|ティッシュ|ティシュ", "ティシュ", text)
    if category in ("kitchen-paper", "tissue"):
        text = re.sub(r"(?<![\d.])(\d+)\s*枚重ね", r"重ね-\1", text)
    if category == "kitchen-paper":
        text = re.sub(r"(?<=\d)\s*カット", "枚", text)
    if category == "sink-net":
        text = re.sub(r"(?<=\d)\s*冊", "袋", text)
    text = CAPACITY.sub(" ", text)
    text = PACK.sub(" ", text)
    text = re.sub(r"(?<![a-z])x(?=\s|$)", " ", text)
    text = re.sub(r"[\s【】()［］\[\]・,:：]", "", DECORATION.sub("", text))
    return PROMOTIONAL.sub("", text)


def comparable_names(left, right, jan, brand, category=None):
    first_name, second_name = identity_text(left, jan, category), identity_text(right, jan, category)
    if isinstance(brand, str) and len(brand.strip()) >= 2:
        maker = identity_text(brand, jan)
        if maker:
            first_name = first_name.removeprefix(maker)
            second_name = second_name.removeprefix(maker)
    return len(first_name) >= 3 and first_name == second_name


def master_identity(row, title, profile, category):
    master = row.get("master_name") or ""
    if (not master or category_rejection(category, title) or category_rejection(category, row["name"])
            or not package_quantity(category, master, profile, directory_name=True)):
        return False
    normalized = identity_text(master, profile.jan, category)
    extra_labels = [identity_text(row.get(key) or "", profile.jan) for key in ("master_brand", "master_maker")]
    extra_labels.append(CATEGORY_LABELS.get(category, ""))
    extra_labels = sorted({label for label in extra_labels if len(label) >= 2}, key=len, reverse=True)
    if len(normalized) < 4 or normalized in extra_labels:
        return False
    def named(value):
        value = identity_text(value, profile.jan, category)
        if normalized not in value:
            return False
        remainder = value.replace(normalized, "", 1)
        for label in extra_labels:
            remainder = remainder.replace(label, "")
        return not NEUTRAL.sub("", remainder)
    return named(row["name"]) and named(title)


def candidates(category, rows, profiles, report):
    by_jan = defaultdict(list)
    existing = {profile.jan for profile in profiles}
    for row in rows:
        if row["jan"] in existing:
            continue
        profile = package_profile(category, row)
        result = rakuten_offer(category, row, profile) if profile else None
        if not result or result[1].total is None:
            report["reasons"]["rakuten_spec_or_offer"] += 1
            report["reasons"]["rakuten_offer" if profile else "rakuten_spec"] += 1
            continue
        by_jan[row["jan"]].append((row, profile, result))
    return sorted(by_jan.values(), key=lambda entries: (
        not any(row.get("prior_match") for row, _, _ in entries),
        -max(row.get("review_count", 0) for row, _, _ in entries), entries[0][1].jan))


def compare_jan(category, entries, hits, client, report):
    matched = defaultdict(list)
    for row, profile, (count, rakuten) in entries:
        for hit in hits:
            name = hit.get("name")
            if (hit.get("janCode") != profile.jan or not isinstance(name, str)
                    or explicit_jans(name) - {profile.jan}
                    or UNSAFE.search(normalize(" ".join(str(hit.get(k) or "") for k in ("name", "headLine", "description"))))
                    or UNKNOWN_PACK.search(normalize(name))):
                report["reasons"]["identity_or_version_conflict"] += 1
                continue
            if package_quantity(category, name, profile) != count:
                report["reasons"]["package_or_category_conflict"] += 1
                continue
            brand = hit.get("brand") or {}
            if (not comparable_names(row["name"], name, profile.jan,
                                     brand.get("name") if isinstance(brand, dict) else "", category)
                    and not master_identity(row, name, profile, category)):
                report["reasons"]["variant_needs_review"] += 1
                continue
            result = yahoo_offer(category, hit, profile, client.affiliate_link)
            if not result or result[1].total is None:
                report["reasons"]["stock_shipping_price_or_link"] += 1
                continue
            matched[count].append((profile, row, rakuten, result[1]))
    groups, sources = [], []
    for count, offers in sorted(matched.items()):
        # One retail JAN and pack cannot authorize conflicting pack dimensions.
        if len({(p.amount, p.unit, p.roll_length_m, p.tissue_pairs, p.kitchen_rolls) for p, _, _, _ in offers}) != 1:
            report["reasons"]["conflicting_dimensions"] += 1
            continue
        # Each display pair must have passed the title comparison together.
        lowest_rakuten = min(item[2].total for item in offers)
        lowest_yahoo = min(item[3].total for item in offers)
        compatible = [item for item in offers if item[2].total == lowest_rakuten and item[3].total == lowest_yahoo]
        if not compatible:
            report["reasons"]["best_offers_have_conflicting_variants"] += 1
            continue
        profile, row, r, y = min(compatible, key=lambda item: (item[2].code, item[3].code))
        label = clean_display_name(row["name"])
        label = re.sub(rf"[（(]{profile.jan}[-_]{count}[)）]", "", label)
        label = DECORATION.sub("", label.replace(profile.jan, ""))
        label = re.sub(r"【\s*】|\(\s*\)|（\s*）|\[\s*\]", "", label).strip()
        groups.append((replace(profile, label=label, label_includes_quantity=True), count, (r, y)))
        sources.append({key: row[key] for key in ("jan", "basis", "item_code", "price", "name", "metric")} |
                       {"pack": count, "url_sha256": hashlib.sha256(r.url.encode()).hexdigest(),
                        "retail_keyword": bool(row.get("retail_keyword"))})
    return groups, sources


def discover(pool, include, client, budget=BUILD_BUDGET, *, keyword_hits=None):
    reports, queues = {}, {}
    groups = defaultdict(list)
    for category, profiles in include.items():
        rows = pool.get(category, [])
        report = {"source_rows": len(rows), "eligible_jans": 0, "queried_jans": 0,
                  "matched_jans": 0, "matched_pairs": 0, "hits": 0, "outcomes": Counter(), "reasons": Counter(), "sources": []}
        reports[category] = report
        queues[category] = candidates(category, rows, profiles, report)
        report["eligible_jans"] = len(queues[category])
    # Round robin preserves a query opportunity for every eligible category.
    for index in range(PER_CATEGORY):
        for category, queue in queues.items():
            if not budget or index >= len(queue):
                continue
            entries = queue[index]
            budget -= 1
            report = reports[category]
            try:
                jan = entries[0][1].jan
                hits = client.search(jan=jan, shipping="free", results=100)
                extra = (keyword_hits or {}).get(category, {}).get(jan, [])
                if extra:
                    by_code = {hit["code"]: hit for hit in extra}
                    by_code.update((hit["code"], hit) for hit in hits if isinstance(hit.get("code"), str))
                    hits = list(by_code.values())
            except YahooUnavailable as error:
                report["api_error"] = str(error)
                return groups, reports
            report["queried_jans"] += 1
            report["hits"] += len(hits)
            if not hits:
                report["reasons"]["no_yahoo_hits"] += 1
            previous_reviews = report["reasons"]["variant_needs_review"]
            selected, sources = compare_jan(category, entries, hits, client, report)
            groups[category].extend(selected)
            outcome = ("matched" if selected else "needs_review" if report["reasons"]["variant_needs_review"] > previous_reviews
                       else "no_yahoo_hits" if not hits else "no_match")
            report["outcomes"][outcome] += 1
            report["sources"].extend(sources)
            report["matched_pairs"] += len(selected)
            report["matched_jans"] += int(bool(selected))
    return groups, reports
