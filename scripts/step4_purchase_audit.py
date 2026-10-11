#!/usr/bin/env python3
"""STEP 4-A: read-only buyer-fit inspection of an already published, trusted catalog.

Never changes product order, pricing, product IDs, affiliate URLs, or the live site.
Does not guess conversion rates, brands, prices, quantity, or unavailable offers.
"""
from __future__ import annotations

import argparse
from collections import Counter
import datetime as dt
import hashlib
import json
import math
from pathlib import Path
import re
from urllib.request import Request, urlopen

from product_quality import REQUIRED, filter_items, item_rejection, parsed_quantity
from tissue_buying_quantity import safe_box_count

SOURCE = "daily-cost purchase fitness audit v1"
CATALOG_URL = "https://stusaurus.github.io/daily-cost-jp/data.json"
MAX_CATALOG_BYTES = 8 * 1024 * 1024
MAX_ITEMS_PER_CATEGORY = 100
REPORT_DIR = Path("audit-results")
# Quantities are in the existing, independently verified comparison unit.
# These are descriptive household-use bands, NOT eligibility or price rules.
BANDS = {
    ("tissue", "box"): (10, 30),
    ("toilet-paper", "roll"): (12, 48),
    ("laundry", "100ml"): (10, 60),
    ("laundry", "100g"): (10, 60),
}


def positive_number(value):
    if type(value) not in (float, int) or not math.isfinite(value) or value <= 0:
        return None
    return value


def hashed_id(row):
    """Stable anonymous public-offer reference, not a claim of brand/SKU identity."""
    if not isinstance(row, dict):
        return None, "UNKNOWN"
    code = row.get("item_code")
    if isinstance(code, str) and code.strip() and len(code) <= 200:
        raw, basis = code.strip(), "ITEM_CODE"
    else:
        url = row.get("url")
        if not isinstance(url, str) or not url.startswith("https://") or len(url) > 1500:
            return None, "UNKNOWN"
        raw, basis = url, "OFFER_URL_ONLY"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20], basis


def band_for(category, metric, qty):
    thresholds = BANDS.get((category, metric))
    if not thresholds or positive_number(qty) is None:
        return "UNKNOWN"
    small_max, bulk_min = thresholds
    if qty <= small_max:
        return "SMALL"
    if qty >= bulk_min:
        return "BULK"
    return "EVERYDAY"


def safe_observation(category_id, row, source, accepted):
    """Re-evaluate quality rules; never trust old flags or claim invalid data is cheap."""
    key, basis = hashed_id(row)
    result = {
        "offer_ref": key, "identity_basis": basis, "source": source,
        "status": "REJECTED", "codes": [], "metric": None,
        "quantity": None, "size_band": "UNKNOWN",
        "price_total_yen": None, "unit_price_yen": None,
        "postage": None, "quantity_evidence": None,
    }
    if not isinstance(row, dict):
        result["codes"].append("NOT_AN_OFFER")
        return result
    result["metric"] = row.get("metric") if isinstance(row.get("metric"), str) else None
    reason = item_rejection(category_id, row)
    if reason:
        result["codes"].append("QUALITY_" + re.sub(r"[^A-Z0-9_]", "_", reason.upper()))
        return result
    if id(row) not in accepted:
        result["codes"].append("ISOLATED_PRICE_OUTLIER")
        return result
    parsed = parsed_quantity(category_id, row["name"])
    if not parsed or positive_number(parsed.get("quantity")) is None:
        result["codes"].append("QUANTITY_UNVERIFIED")
        return result
    result.update({
        "status": "VERIFIED",
        "quantity": parsed["quantity"],
        "size_band": band_for(category_id, row["metric"], parsed["quantity"]),
        "price_total_yen": row["price"],
        "unit_price_yen": row["unit_price"],
        "postage": row["postage"],
        "quantity_evidence": str(parsed.get("evidence") or "")[:100],
    })
    if result["size_band"] == "UNKNOWN":
        result["codes"].append("HOUSEHOLD_SIZE_THRESHOLD_NOT_DEFINED")
    if basis != "ITEM_CODE":
        result["codes"].append("SAME_SKU_UNVERIFIED")
    return result


def inspect_category(category_id, category):
    if not isinstance(category, dict):
        return {"status": "UNAVAILABLE", "codes": ["CATEGORY_MISSING"], "offers": [],
                "coverage": None, "reject_reasons": None}
    if category.get("error"):
        return {"status": "UNAVAILABLE", "codes": ["CATEGORY_FETCH_ERROR"], "offers": [],
                "coverage": None, "reject_reasons": None}
    raw = category.get("items")
    if (not isinstance(raw, list) or len(raw) > MAX_ITEMS_PER_CATEGORY or
            any(not isinstance(row, dict) or not isinstance(row.get("name"), str)
                for row in raw)):
        return {"status": "UNAVAILABLE", "codes": ["INVALID_CATEGORY_ITEMS"], "offers": [],
                "coverage": None, "reject_reasons": None}
    # filter_items is the same existing strict quality and price-outlier gate.
    # Passing its entire result (not single rows) preserves outlier context.
    accepted_rows = filter_items(category_id, raw)
    accepted = set()
    used = set()
    # Match copies from the existing gate to originals without trusting flags.
    # Key by (identity, occurrence); if duplicated, retain the first occurrence.
    for good in accepted_rows:
        for index, candidate in enumerate(raw):
            if index not in used and isinstance(candidate, dict) and all(
                    candidate.get(k) == good.get(k) for k in
                    ("name", "url", "price", "unit_price", "metric", "confidence", "postage")):
                accepted.add(id(candidate))
                used.add(index)
                break

    observations = [safe_observation(category_id, row, "RANKING", accepted) for row in raw]
    # Tissue small-pack is a separately vetted candidate, not a ranking replacement.
    if category_id == "tissue" and category.get("small_pack_offer") is not None:
        extra = category["small_pack_offer"]
        if isinstance(extra, dict) and safe_box_count(extra) is not None:
            observations.append(safe_observation(category_id, extra, "TISSUE_SMALL_SUPPLEMENT", {id(extra)}))
        else:
            observations.append({"status": "REJECTED", "source": "TISSUE_SMALL_SUPPLEMENT",
                                 "offer_ref": None, "codes": ["SUPPLEMENT_NOT_VERIFIED"],
                                 "size_band": "UNKNOWN"})

    # STEP5 candidates are separate from ranking, but the audit must see them.
    pool = category.get('purpose_candidates', [])
    if isinstance(pool, list) and len(pool) <= 30 and all(isinstance(r, dict) for r in pool):
        good_pool = filter_items(category_id, pool)
        fields = ('name', 'url', 'price', 'unit_price', 'metric', 'confidence', 'postage', 'item_code')
        approved = {id(r) for r in pool if any(all(r.get(k) == g.get(k) for k in fields) for g in good_pool)}
        from step4_recommendations import destination_matches, sale_band
        from comparison_units import comparison_unit
        for row in pool:
            observation = safe_observation(category_id, row, 'PURPOSE_SUPPLEMENT', approved)
            if observation['status'] == 'VERIFIED':
                if not destination_matches(row) or not comparison_unit(category_id, row):
                    observation.update(status='REJECTED', codes=['PURPOSE_IDENTITY_OR_UNIT_UNCONFIRMED'])
                else:
                    observation['size_band'] = (sale_band(category_id, row, observation['quantity']) or 'UNKNOWN').upper()
            observations.append(observation)
    else:
        observations.append({'status':'REJECTED','source':'PURPOSE_SUPPLEMENT','offer_ref':None,
                             'codes':['INVALID_PURPOSE_SUPPLEMENT'],'size_band':'UNKNOWN'})

    seen = set()
    unique = []
    codes = []
    for item in observations:
        if item["status"] != "VERIFIED":
            continue
        identifier = item.get("offer_ref")
        if identifier and identifier in seen:
            item["codes"].append("DUPLICATE_OFFER_ID")
            codes.append("DUPLICATE_OFFER_ID")
            continue
        if identifier:
            seen.add(identifier)
        else:
            item["codes"].append("OFFER_ID_UNKNOWN")
        unique.append(item)
    # A duplicate public offer is not a distinct choice. Different shop item
    # codes alone do not prove different underlying brand/SKU products.
    coverage = {
        "verified_offers": len(unique),
        "distinct_item_codes": len({i["offer_ref"] for i in unique if i["identity_basis"] == "ITEM_CODE"}),
        "identity_uncertain": sum(i["identity_basis"] != "ITEM_CODE" for i in unique),
        "small": sum(i["size_band"] == "SMALL" for i in unique),
        "everyday_including_small": sum(i["size_band"] in ("SMALL", "EVERYDAY") for i in unique),
        "bulk": sum(i["size_band"] == "BULK" for i in unique),
        "unknown_size": sum(i["size_band"] == "UNKNOWN" for i in unique),
    }
    if not unique:
        codes.append("NO_VERIFIED_OFFERS_IN_SNAPSHOT")
    elif any((category_id, i.get("metric")) in BANDS for i in unique):
        if coverage["everyday_including_small"] == 0:
            codes.append("NO_VERIFIED_HOUSEHOLD_SIZE_IN_SNAPSHOT")
        if coverage["small"] == 0:
            codes.append("NO_VERIFIED_SMALL_SIZE_IN_SNAPSHOT")
    if coverage["identity_uncertain"]:
        codes.append("SKU_DIVERSITY_UNVERIFIED")
    rejects = Counter(code for item in observations if item["status"] != "VERIFIED"
                      for code in item.get("codes", []))
    return {
        "status": "ASSESSED" if unique else "NO_VERIFIED_OFFERS",
        "codes": sorted(set(codes)),
        "coverage": coverage,
        "reject_reasons": dict(sorted(rejects.items())),
        "offers": observations,
        "recommendation_action": "READ_ONLY_INVESTIGATE",
        "ranking_changed": False,
    }


def verify_snapshot(snapshot, now=None):
    if not isinstance(snapshot, dict) or snapshot.get("source") != "Rakuten Ichiba API" or (
            snapshot.get("ranking_basis") != "shipping_included_unit_price"):
        return "UNTRUSTED_SNAPSHOT"
    if not isinstance(snapshot.get("categories"), dict):
        return "UNTRUSTED_SNAPSHOT"
    try:
        stamp = dt.datetime.fromisoformat(snapshot["updated_at"].replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            return "UNKNOWN_TIMESTAMP"
        hours = ((now or dt.datetime.now(dt.timezone.utc)) - stamp).total_seconds() / 3600
        if hours < -1:
            return "FUTURE_SNAPSHOT"
        if hours > 72:
            return "STALE_SNAPSHOT"
    except (TypeError, ValueError, AttributeError, KeyError):
        return "UNKNOWN_TIMESTAMP"
    return "TRUSTED_RECENT"


def inspect(snapshot, *, now=None, fetch_status="AVAILABLE"):
    status = verify_snapshot(snapshot, now) if snapshot is not None else "UNAVAILABLE"
    report = {
        "source": SOURCE, "status": status, "fetch_status": fetch_status,
        "generated_at_utc": (now or dt.datetime.now(dt.timezone.utc)).isoformat(),
        "catalog_updated_at": snapshot.get("updated_at") if isinstance(snapshot, dict) else None,
        "published_source": CATALOG_URL,
        "recommendation_changes": "NONE", "published_changes": False,
        "affiliate_sales_status": "NOT_CONNECTED",
        "real_user_conversion_status": "NOT_EVALUATED",
        "search_price_failure_breakdown": "NOT_IN_PUBLISHED_SNAPSHOT",
        "brand_request_match": "NOT_EVALUATED_WITHOUT_EXPLICIT_BRAND_REQUEST",
        "categories": {},
    }
    if status != "TRUSTED_RECENT":
        return report
    for category_id in sorted(REQUIRED):
        report["categories"][category_id] = inspect_category(
            category_id, snapshot["categories"].get(category_id))
    if any(v["status"] == "UNAVAILABLE" for v in report["categories"].values()):
        report["status"] = "PARTIAL"
    return report


def markdown(report):
    lines = [
        "# STEP 4 買い物客視点の購買適合性監査（読み取り専用）", "",
        "- 判定: " + report["status"],
        "- 公開スナップショット更新時刻: " + str(report["catalog_updated_at"]),
        "- 商品・価格・送料・楽天リンク・ランキング変更: なし",
        "- 実売上: 未接続／評価不能。クリックと売上を混同しない。",
        "- ブランド照合・商品検索での0件原因: この公開データだけでは未判定。",
        "- 少量・日常・大量の区分は指定3カテゴリの確認可能数量だけを説明する目安であり、ランキングや掲載可否を変更しない。", "",
        "| カテゴリ | 状態 | 検証済み候補 | 少量 | 日常（少量含む） | 大量 | 診断 |",
        "|---|---|---:|---:|---:|---:|---|",
    ]
    for cat, result in report["categories"].items():
        coverage = result.get("coverage") or {}
        count = lambda key: str(coverage[key]) if key in coverage else "不明"
        lines.append("| " + cat + " | " + result["status"] + " | " +
                     " | ".join(count(k) for k in (
                         "verified_offers", "small", "everyday_including_small", "bulk")) +
                     " | " + ", ".join(result["codes"][:4]) + " |")
    if not report["categories"]:
        lines += ["| - | UNAVAILABLE | 不明 | 不明 | 不明 | 不明 | 信頼できる最新の入力がない |"]
    lines += ["", "判断根拠と商品別のコード・数量・支払総額はJSONに保存。",
              "同一商品であることをブランド・商品名だけから推測しない。",
              "不明・除外を0件の実需要や売上0円と解釈しない。",
              "このステップはレポートのみ。表示変更・Draft修正PR発行・自動公開は未実装。", ""]
    return "\n".join(lines)


def load_live():
    request = Request(CATALOG_URL, headers={"User-Agent": "DailyCost-PurchaseAudit/1.0",
                                          "Accept": "application/json"})
    with urlopen(request, timeout=25) as response:
        if response.status != 200:
            raise ValueError("Catalog HTTP status is not 200")
        data = response.read(MAX_CATALOG_BYTES + 1)
    if len(data) > MAX_CATALOG_BYTES:
        raise ValueError("Catalog exceeds bounded download size")
    return json.loads(data)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, help="Trusted local site/data.json; omit to read public URL")
    parser.add_argument("--out", type=Path, default=REPORT_DIR)
    args = parser.parse_args()
    try:
        if args.input:
            raw = args.input.read_bytes()
            if len(raw) > MAX_CATALOG_BYTES:
                raise ValueError("Catalog exceeds bounded local size")
            snapshot = json.loads(raw)
        else:
            snapshot = load_live()
        report = inspect(snapshot)
    except (OSError, ValueError, TimeoutError, json.JSONDecodeError) as exc:
        # Not a successful empty catalog; source unavailable means no claims.
        report = inspect(None, fetch_status="UNAVAILABLE_OR_INVALID_" + type(exc).__name__.upper())
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "step4-purchase-fitness.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    (args.out / "step4-purchase-fitness.md").write_text(markdown(report), encoding="utf-8")
    print("STEP 4 read-only purchase fitness: " + report["status"])
    if report["status"] != "TRUSTED_RECENT":
        print("No automatic recommendation or publication permitted.")


if __name__ == "__main__":
    main()
