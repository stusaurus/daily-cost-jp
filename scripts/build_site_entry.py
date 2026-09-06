"""Runtime entry point for the 2026-07-01 Rakuten Ichiba API response shape."""
import json
import re
import time
import urllib.parse
import urllib.request

import build_site as core


def to_base_amount(amount, unit):
    unit = unit.lower()
    amount = float(amount)
    if unit == "kg":
        return "weight", amount * 1000
    if unit == "g":
        return "weight", amount
    if unit == "l":
        return "volume", amount * 1000
    if unit == "ml":
        return "volume", amount
    return None, None


def result_from_total(kind, total, category_kind, confidence, evidence):
    if not total or total <= 0:
        return None
    if kind == "weight":
        metric = "100g"
        quantity = total / 100
    else:
        metric = "1L" if category_kind == "water" else "100ml"
        quantity = total / (1000 if metric == "1L" else 100)

    if category_kind == "coffee" and metric != "100g":
        return None
    if quantity <= 0:
        return None
    return {
        "metric": metric,
        "quantity": quantity,
        "confidence": confidence,
        "evidence": evidence,
    }


def safer_parse_measure_quantity(title, category_kind):
    """Reject variant titles unless all visible capacity evidence agrees."""
    text = core.normalize_text(title)

    explicit_matches = list(re.finditer(
        r"(\d+(?:\.\d+)?)\s*(kg|g|ml|l)\s*x\s*(\d+)",
        text,
        flags=re.IGNORECASE,
    ))
    if explicit_matches:
        totals = []
        kinds = []
        for match in explicit_matches:
            kind, base = to_base_amount(match.group(1), match.group(2))
            totals.append(base * int(match.group(3)))
            kinds.append(kind)
        if len(set(kinds)) != 1 or max(totals) - min(totals) > 0.001:
            return None

        chosen = explicit_matches[0]
        chosen_kind = kinds[0]
        chosen_total = totals[0]

        # If the title also advertises a different standalone capacity, it is
        # probably a selectable variant. Do not bind the minimum price to it.
        all_measures = re.findall(
            r"(\d+(?:\.\d+)?)\s*(kg|g|ml|l)",
            text,
            flags=re.IGNORECASE,
        )
        visible_bases = []
        for amount, unit in all_measures:
            kind, base = to_base_amount(amount, unit)
            if kind == chosen_kind:
                visible_bases.append(base)
        explicit_base = to_base_amount(chosen.group(1), chosen.group(2))[1]
        if any(abs(base - explicit_base) > 0.001 and abs(base - chosen_total) > 0.001 for base in visible_bases):
            return None

        return result_from_total(
            chosen_kind,
            chosen_total,
            category_kind,
            0.99,
            chosen.group(0),
        )

    all_measures = re.findall(
        r"(\d+(?:\.\d+)?)\s*(kg|g|ml|l)",
        text,
        flags=re.IGNORECASE,
    )
    if len(all_measures) != 1:
        return None

    amount, unit = all_measures[0]
    kind, base = to_base_amount(amount, unit)
    if not kind or not base:
        return None

    # Support titles such as "【6個】...1490g" only when exactly one packaging
    # count is visible. This prevents underestimating multi-pack detergent prices.
    pack_counts = [
        int(value)
        for value, pack_unit in re.findall(
            r"(\d+)\s*(個|袋|本|パック|セット)",
            text,
            flags=re.IGNORECASE,
        )
        if int(value) > 1
    ]
    if len(pack_counts) == 1:
        total = base * pack_counts[0]
        evidence = f"{pack_counts[0]}個相当 × {amount}{unit}"
        confidence = 0.94
    elif len(pack_counts) == 0:
        total = base
        evidence = f"{amount}{unit}"
        confidence = 0.88
    else:
        return None

    return result_from_total(kind, total, category_kind, confidence, evidence)


def safer_parse_count_quantity(title, allowed_units):
    text = core.normalize_text(title)
    units_re = "|".join(re.escape(unit) for unit in allowed_units)

    explicit_matches = list(re.finditer(
        rf"(\d+(?:\.\d+)?)\s*({units_re})\s*x\s*(\d+)",
        text,
        flags=re.IGNORECASE,
    ))
    if explicit_matches:
        totals = [float(m.group(1)) * int(m.group(3)) for m in explicit_matches]
        if max(totals) - min(totals) > 0.001:
            return None
        total = totals[0]
        if total > 0 and float(total).is_integer():
            return {
                "metric": allowed_units[explicit_matches[0].group(2)],
                "quantity": total,
                "confidence": 0.99,
                "evidence": explicit_matches[0].group(0),
            }

    singles = list(re.finditer(
        rf"(\d+(?:\.\d+)?)\s*({units_re})",
        text,
        flags=re.IGNORECASE,
    ))
    if not singles:
        return None

    values = [float(m.group(1)) for m in singles]
    # Multiple different standalone counts usually mean selectable variants.
    # Allow them only when the largest value agrees with a known explicit total.
    if len(set(values)) > 1:
        return None

    total = values[0]
    if total > 0 and total.is_integer():
        return {
            "metric": allowed_units[singles[0].group(2)],
            "quantity": total,
            "confidence": 0.88,
            "evidence": singles[0].group(0),
        }
    return None


def category_is_suitable(category_id, title):
    exclusions = {
        "tissue": ("ウェット", "ウエット", "おしり", "手口", "除菌シート", "ペーパータオル", "キッチンペーパー"),
        "dish": ("ディスペンサー", "ハンドソープ", "ソープディスペンサー", "洗濯用"),
        "water": ("炭酸", "スパークリング"),
    }
    if any(term in title for term in exclusions.get(category_id, ())):
        return False

    if category_id == "dish" and not any(term in title for term in ("食器", "台所", "キッチン", "ジョイ", "キュキュット", "チャーミー", "ヤシノミ")):
        return False

    return True


def fetch_page(category, page):
    params = {
        "applicationId": core.APP_ID,
        "keyword": category["keyword"],
        "NGKeyword": "ふるさと納税",
        "hits": 30,
        "page": page,
        "formatVersion": 2,
        "format": "json",
        "hasReviewFlag": 1,
        "imageFlag": 1,
        "sort": "-reviewCount",
    }
    if core.AFFILIATE_ID:
        params["affiliateId"] = core.AFFILIATE_ID

    url = core.API_URL + "?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(
        url,
        headers={
            "accessKey": core.ACCESS_KEY,
            "Origin": "https://stusaurus.github.io",
            "Referer": core.SITE_URL,
            "User-Agent": "daily-cost-jp/0.5",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return payload.get("Items") or payload.get("items") or []


def fetch_category(category):
    raw_items = fetch_page(category, 1)
    normalized = [core.normalize_item(raw, category) for raw in raw_items]

    excluded = ("ふるさと納税", "返礼品")
    filtered = [
        item
        for item in normalized
        if item.get("price", 0) > 0
        and item.get("url")
        and not any(term in item.get("name", "") for term in excluded)
        and category_is_suitable(category["id"], item.get("name", ""))
    ]

    # If strict filtering leaves too little comparison data, safely inspect a
    # second page while respecting the registered 1 QPS rate.
    metric, ranked = core.choose_ranked_items(filtered)
    if len(ranked) < 5:
        time.sleep(1.1)
        raw_more = fetch_page(category, 2)
        more = [core.normalize_item(raw, category) for raw in raw_more]
        filtered.extend(
            item
            for item in more
            if item.get("price", 0) > 0
            and item.get("url")
            and not any(term in item.get("name", "") for term in excluded)
            and category_is_suitable(category["id"], item.get("name", ""))
        )

    return filtered


core.parse_measure_quantity = safer_parse_measure_quantity
core.parse_count_quantity = safer_parse_count_quantity
core.fetch_category = fetch_category

if __name__ == "__main__":
    core.build_site()
