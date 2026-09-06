"""Runtime entry point for the 2026-07-01 Rakuten Ichiba API response shape."""
import json
import urllib.parse
import urllib.request

import build_site as core


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
            "User-Agent": "daily-cost-jp/0.3",
        },
    )

    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))

    raw_items = payload.get("Items") or payload.get("items") or []
    normalized = [core.normalize_item(raw, category) for raw in raw_items]

    # Keep ordinary retail items only. API-side NGKeyword is the first line of defense;
    # this local filter protects against variations in wording.
    excluded = ("ふるさと納税", "返礼品")
    return [
        item
        for item in normalized
        if not any(term in item.get("name", "") for term in excluded)
    ]


core.fetch_category = fetch_category

if __name__ == "__main__":
    core.build_site()
