"""Discover retail packages from this build's validated Rakuten acquisition pool."""
from collections import Counter, defaultdict
from dataclasses import replace
from decimal import Decimal
import hashlib
import re
from urllib.parse import parse_qs

from comparison_units import toilet_ply_length
from marketplace_offers import (AMBIGUOUS, CAPACITY, CATALOG_UNITS, Product,
                               explicit_jans, first, known_shipping, package_quantity,
                               rakuten_offer, rakuten_product_link, valid_jan, yahoo_offer)
from product_display import clean_display_name
from product_quality import category_rejection
from sale_quantity import normalize, parse_sale_quantity
from yahoo_shopping import YahooUnavailable, safe_url

# One request per distinct JAN. The established profiles always run first.
PER_CATEGORY = 12
BUILD_BUDGET = 120
GTIN = re.compile(r"(?<!\d)\d{13}(?!\d)")
CAPTION_JAN = re.compile(r"(?:jan(?:コード)?|バーコード)\s*[:：]?\s*(\d{13})(?!\d)", re.I)
UNSAFE = re.compile(r"選択|選んで|いずれか|旧(?:型|商品|モデル|仕様|処方|デザイン|タイプ)|リニューアル|新旧|訳あり|福袋|ランダム|おまけ|景品|プレゼント付|種類指定不可|パッケージ.{0,8}(?:異なる|変更)|定期購入|定期便")
PACK = re.compile(r"(?<![\d.])\d+\s*(?:ロール|パック|ケース|セット|枚|個|本|箱|袋)(?:入り?)?")
DECORATION = re.compile(r"送料無料|送料込み|まとめ買い|ケース販売|ケース売り|公式ショップ|公式ストア|税込")
REFILL = re.compile(r"(?:詰|つ)め?(?:替|か)え?(?:用)?")

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
    labelled = set(CAPTION_JAN.findall(caption))
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
    if UNSAFE.search(text) or AMBIGUOUS.search(text) or category_rejection(category, text):
        return None
    tissue_pairs = roll_length = None
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
    else:
        quantity = parse_sale_quantity(text)
        if not quantity or quantity["kind"] != "count":
            return None
        unit = quantity["count_unit"]
        amount = quantity["total_count"] // (quantity.get("outer_count") or 1)
        if CATALOG_UNITS.get(unit) != row["metric"]:
            return None
    if amount <= 0:
        return None
    return Product(jan, clean_display_name(name), int(amount), unit, (), "",
                   roll_length_m=roll_length, tissue_pairs=tissue_pairs,
                   rakuten_evidence=((row["item_code"], product_path(row)),))


def identity_text(name, jan):
    # Retain all product words, formula, size, fragrance, model and manufacturer.
    # Remove only presentation and quantities which are checked independently.
    text = normalize(clean_display_name(name)).lower().replace(jan, "")
    text = REFILL.sub("詰替", text)
    text = CAPACITY.sub(" ", text)
    text = PACK.sub(" ", text)
    text = re.sub(r"(?<![a-z])x(?=\s|$)", " ", text)
    return re.sub(r"[\s【】()［］\[\]・,:：]", "", DECORATION.sub("", text))


def comparable_names(left, right, jan, brand):
    first_name, second_name = identity_text(left, jan), identity_text(right, jan)
    if isinstance(brand, str) and len(brand.strip()) >= 2:
        maker = identity_text(brand, jan)
        if maker:
            first_name = first_name.removeprefix(maker)
            second_name = second_name.removeprefix(maker)
    return len(first_name) >= 3 and first_name == second_name


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
            continue
        by_jan[row["jan"]].append((row, profile, result))
    return sorted(by_jan.values(), key=lambda entries: (
        -max(row.get("review_count", 0) for row, _, _ in entries), entries[0][1].jan))


def compare_jan(category, entries, hits, client, report):
    matched = defaultdict(list)
    for row, profile, (count, rakuten) in entries:
        for hit in hits:
            name = hit.get("name")
            if (hit.get("janCode") != profile.jan or not isinstance(name, str)
                    or explicit_jans(name) - {profile.jan} or UNSAFE.search(normalize(name))):
                report["reasons"]["identity_or_version_conflict"] += 1
                continue
            if package_quantity(category, name, profile) != count:
                report["reasons"]["package_or_category_conflict"] += 1
                continue
            brand = hit.get("brand") or {}
            if not comparable_names(row["name"], name, profile.jan,
                                    brand.get("name") if isinstance(brand, dict) else ""):
                report["reasons"]["variant_needs_review"] += 1
                continue
            result = yahoo_offer(category, hit, profile, client.affiliate_link)
            if not result or result[1].total is None:
                report["reasons"]["stock_shipping_price_or_link"] += 1
                continue
            matched[count].append((profile, row, rakuten, result[1]))
    groups, sources = [], []
    for count, offers in sorted(matched.items()):
        # Each display pair must have passed the title comparison together.
        profile, row, r, y = min(offers, key=lambda item: (item[2].total + item[3].total,
                                                            item[2].total, item[2].code, item[3].code))
        label = DECORATION.sub("", clean_display_name(row["name"]).replace(profile.jan, "")).strip()
        groups.append((replace(profile, label=label, label_includes_quantity=True), count, (r, y)))
        sources.append({key: row[key] for key in ("jan", "basis", "item_code", "price", "name", "metric")} |
                       {"pack": count, "url_sha256": hashlib.sha256(r.url.encode()).hexdigest()})
    return groups, sources


def discover(pool, include, client, budget=BUILD_BUDGET):
    reports, queues = {}, {}
    groups = defaultdict(list)
    for category, profiles in include.items():
        rows = pool.get(category, [])
        report = {"source_rows": len(rows), "eligible_jans": 0, "queried_jans": 0,
                  "matched_jans": 0, "matched_pairs": 0, "hits": 0, "reasons": Counter(), "sources": []}
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
                hits = client.search(jan=entries[0][1].jan, shipping="free")
            except YahooUnavailable as error:
                report["api_error"] = str(error)
                return groups, reports
            report["queried_jans"] += 1
            report["hits"] += len(hits)
            if not hits:
                report["reasons"]["no_yahoo_hits"] += 1
            selected, sources = compare_jan(category, entries, hits, client, report)
            groups[category].extend(selected)
            report["sources"].extend(sources)
            report["matched_pairs"] += len(selected)
            report["matched_jans"] += int(bool(selected))
    return groups, reports
