from __future__ import annotations

import json
import sys
import time
import urllib.parse
import urllib.request

API = "https://daily-cost-api.kiyo0625puma.workers.dev/api/product-search"
QUERIES = ["おしりセレブ", "アリエール", "ボールド", "キレイキレイ"]


def fetch_json(url: str, attempts: int = 3):
    last_error = None
    for attempt in range(attempts):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "daily-cost-jp-smoke/1.0"})
            with urllib.request.urlopen(req, timeout=60) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            last_error = exc
            if attempt < attempts - 1:
                time.sleep(4 * (attempt + 1))
    raise RuntimeError(last_error)


def main() -> int:
    failures: list[str] = []

    for i, query in enumerate(QUERIES):
        if i:
            time.sleep(2)
        url = API + "?" + urllib.parse.urlencode({"q": query, "hits": 10})
        try:
            data = fetch_json(url)
        except Exception as exc:
            failures.append(f"{query}: request failed: {exc}")
            continue

        if data.get("error"):
            failures.append(f"{query}: API error: {data.get('error')}")
            continue

        products = data.get("products") or []
        if not products:
            failures.append(f"{query}: no products returned")
            continue

        priced = [p for p in products if int(p.get("shipping_included_price") or 0) > 0]
        broken_links = [p.get("name", "") for p in priced if not p.get("shipping_included_url")]

        print(
            f"{query}: products={len(products)} "
            f"priced={len(priced)} shipping_candidates={data.get('shipping_lookup_count', 0)}"
        )
        for p in priced[:3]:
            print(
                "  -",
                p.get("name", "")[:80],
                "=>",
                p.get("shipping_included_price"),
                "yen",
                "image=matched" if p.get("shipping_included_image") else "image=base",
            )

        if broken_links:
            failures.append(f"{query}: priced products missing destination URL: {broken_links[:3]}")

    if failures:
        print("\nSMOKE TEST FAILED", file=sys.stderr)
        for failure in failures:
            print("-", failure, file=sys.stderr)
        return 1

    print("\nSMOKE TEST PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
