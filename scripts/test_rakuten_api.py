# Rakuten API connectivity check for daily-cost-jp
import json
import os
import sys
import urllib.parse
import urllib.request

APP_ID = os.environ.get("RAKUTEN_APPLICATION_ID")
ACCESS_KEY = os.environ.get("RAKUTEN_ACCESS_KEY")
AFFILIATE_ID = os.environ.get("RAKUTEN_AFFILIATE_ID", "")

if not APP_ID or not ACCESS_KEY:
    print("Missing required Rakuten secrets.", file=sys.stderr)
    sys.exit(2)

params = {
    "applicationId": APP_ID,
    "keyword": "トイレットペーパー",
    "hits": 3,
    "formatVersion": 2,
    "format": "json",
}
if AFFILIATE_ID:
    params["affiliateId"] = AFFILIATE_ID

url = (
    "https://openapi.rakuten.co.jp/ichibams/api/IchibaItem/Search/20260701?"
    + urllib.parse.urlencode(params)
)

request = urllib.request.Request(
    url,
    headers={
        "accessKey": ACCESS_KEY,
        "Origin": "https://stusaurus.github.io",
        "Referer": "https://stusaurus.github.io/daily-cost-jp/",
        "User-Agent": "daily-cost-jp/0.1",
    },
)

try:
    with urllib.request.urlopen(request, timeout=30) as response:
        body = response.read().decode("utf-8")
        data = json.loads(body)
except Exception as exc:
    print(f"Rakuten API request failed: {exc}", file=sys.stderr)
    sys.exit(1)

print("Top-level keys:", sorted(data.keys()))
print("count=", data.get("count"), "hits=", data.get("hits"), "pageCount=", data.get("pageCount"))
items = data.get("Items") or data.get("items") or []
print(f"items length: {len(items)}")
if items and isinstance(items[0], dict):
    print("First item keys:", sorted(items[0].keys()))
if "error" in data:
    print("API error:", data.get("error"), data.get("error_description"))

for index, item in enumerate(items[:3], start=1):
    item = item.get("Item", item.get("item", item)) if isinstance(item, dict) else {}
    print(
        f"{index}. {item.get('itemName', '')[:80]} | "
        f"¥{item.get('itemPrice', '?')} | "
        f"review={item.get('reviewAverage', '?')}"
    )
