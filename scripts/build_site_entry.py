"""Runtime entry point for the 2026-07-01 Rakuten Ichiba API response shape."""
import json
import re
import urllib.parse
import urllib.request

import build_site as core


def safer_parse_measure_quantity(title, category_kind):
    """Only calculate a single-size title when the capacity is unambiguous."""
    text = core.normalize_text(title)

    explicit = re.search(
        r"(\d+(?:\.\d+)?)\s*(kg|g|ml|l)\s*x\s*(\d+)",
        text,
        flags=re.IGNORECASE,
    )
    if explicit:
        amount = float(explicit.group(1))
        unit = explicit.group(2).lower()
        multiplier = int(explicit.group(3))
        confidence = 0.99
        evidence = explicit.group(0)
    else:
        # Titles that mention several alternative capacities often represent
        # selectable variants. Using the first number can produce a false unit price.
        all_measures = re.findall(
            r"(\d+(?:\.\d+)?)\s*(kg|g|ml|l)",
            text,
            flags=re.IGNORECASE,
        )
        if len(all_measures) != 1:
            return None
        amount = float(all_measures[0][0])
        unit = all_measures[0][1].lower()
        multiplier = 1
        confidence = 0.88
        evidence = f"{all_measures[0][0]}{all_measures[0][1]}"

    if amount <= 0 or multiplier <= 0:
        return None

    if unit == "kg":
        total_g = amount * 1000 * multiplier
        metric = "100g"
        quantity = total_g / 100
    elif unit == "g":
        total_g = amount * multiplier
        metric = "100g"
        quantity = total_g / 100
    elif unit == "l":
        total_ml = amount * 1000 * multiplier
        metric = "1L" if category_kind == "water" else "100ml"
        quantity = total_ml / (1000 if metric == "1L" else 100)
    else:
        total_ml = amount * multiplier
        metric = "1L" if category_kind == "water" else "100ml"
        quantity = total_ml / (1000 if metric == "1L" else 100)

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


def category_is_suitable(category_id, title):
    exclusions = {
        "tissue": ("ウェット", "ウエット", "おしり", "手口", "除菌シート", "ペーパータオル", "キッチンペーパー"),
        "dish": ("ディスペンサー", "ハンドソープ", "ソープディスペンサー"),
        "water": ("炭酸", "スパークリング"),
    }
    if any(term in title for term in exclusions.get(category_id, ())):
        return False

    if category_id == "dish" and not any(term in title for term in ("食器", "台所", "キッチン", "ジョイ", "キュキュット", "チャーミー", "ヤシノミ")):
        return False

    return True


def fetch_category(category):
    params = {
        "applicationId": core.APP_ID,
        "keyword": category["keyword"],
        "NGKeyword": "ふるさと納税",
        "hits": 30,
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
            "User-Agent": "daily-cost-jp/0.4",
        },
    )

    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))

    raw_items = payload.get("Items") or payload.get("items") or []
    normalized = [core.normalize_item(raw, category) for raw in raw_items]

    excluded = ("ふるさと納税", "返礼品")
    return [
        item
        for item in normalized
        if item.get("price", 0) > 0
        and item.get("url")
        and not any(term in item.get("name", "") for term in excluded)
        and category_is_suitable(category["id"], item.get("name", ""))
    ]


core.parse_measure_quantity = safer_parse_measure_quantity
core.fetch_category = fetch_category

if __name__ == "__main__":
    core.build_site()
