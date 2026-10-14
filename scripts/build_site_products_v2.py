"""Compatibility entry point for Rakuten Product Search API response shape."""
import json
import urllib.parse
import urllib.request

import build_site_products as products


def fetch_product_page_fixed(category, page):
    params = {
        "applicationId": products.APP_ID,
        "keyword": category["name"],
        "hits": 30,
        "page": page,
        "format": "json",
        "formatVersion": 2,
        "elements": ",".join([
            "productId", "productCode", "productName", "productNo", "brandName",
            "productUrlPC", "affiliateUrl", "mediumImageUrl", "salesItemCount",
            "usedExcludeSalesMinPrice", "salesMinPrice", "averagePrice",
            "reviewCount", "reviewAverage", "genreName"
        ]),
    }
    if products.AFFILIATE_ID:
        params["affiliateId"] = products.AFFILIATE_ID

    url = products.PRODUCT_API_URL + "?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(
        url,
        headers={
            "accessKey": products.ACCESS_KEY,
            "Origin": "https://stusaurus.github.io",
            "Referer": products.core.SITE_URL,
            "User-Agent": "daily-cost-jp/0.6",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))

    raw_rows = payload.get("Products") or payload.get("items") or []
    rows = []
    for row in raw_rows:
        if isinstance(row, dict):
            rows.append(row.get("Product", row))
    return rows


products.fetch_product_page = fetch_product_page_fixed

if __name__ == "__main__":
    products.main()
