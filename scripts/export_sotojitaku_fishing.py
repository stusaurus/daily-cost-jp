#!/usr/bin/env python3
"""Export a verified SOTOJITAKU FISHING Rakuten catalog.

Runs in daily-cost-jp because this repository already owns the Rakuten API
credentials. Product intent/spec metadata remains authoritative in the
SOTOJITAKU repository; this script only resolves current live Rakuten listings
and affiliate URLs.

The exporter is fail-closed per product:
- current listing must be sold by the same Rakuten shop as the audited seed
- all identity groups must match the current listing name
- forbidden terms must not appear
- price, image, item URL and affiliate URL must be present
- affiliate URL must target the exact current item URL

The output may be partial. SOTOJITAKU performs its own core-coverage gate before
adopting the catalog.
"""
from __future__ import annotations

import json
import os
import re
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SEED_DIR = Path(os.environ.get("FISHING_SEED_DIR", "/tmp/sotojitaku/fishing/data/product-seeds"))
OUT = Path(os.environ.get(
    "FISHING_EXPORT_OUT",
    str(ROOT / "shared-data" / "sotojitaku-fishing-products.json"),
))

RAKUTEN_API = "https://openapi.rakuten.co.jp/ichibams/api/IchibaItem/Search/20260701"
HEADERS = {
    "Origin": "https://stusaurus.github.io",
    "Referer": "https://stusaurus.github.io/sotojitaku/fishing/",
    "User-Agent": "daily-cost-jp-sotojitaku-fishing-export/1.0",
}
_LAST_API_CALL = 0.0
MIN_API_INTERVAL_SECONDS = 1.05


def compact(value: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", str(value or ""))).lower()


def canonical_item_url(value: str) -> str:
    value = str(value or "")
    parsed = urllib.parse.urlparse(value)
    if parsed.hostname == "hb.afl.rakuten.co.jp":
        value = urllib.parse.parse_qs(parsed.query).get("pc", [""])[0]
        parsed = urllib.parse.urlparse(value)
    if parsed.scheme != "https" or parsed.hostname != "item.rakuten.co.jp":
        return ""
    path = re.sub(r"/+", "/", parsed.path).rstrip("/") + "/"
    return "https://item.rakuten.co.jp" + path


def rakuten_shop(value: str) -> str:
    parsed = urllib.parse.urlparse(canonical_item_url(value))
    parts = [p for p in parsed.path.split("/") if p]
    return parts[0] if parts else ""


def identity_ok(name: str, seed: dict) -> bool:
    normalized = compact(name)
    if any(compact(term) in normalized for term in seed.get("forbiddenTerms", [])):
        return False
    groups = seed.get("identityGroups", [])
    return all(any(compact(term) in normalized for term in group) for group in groups)


def seed_queries(seed: dict) -> list[str]:
    values = seed.get("searchQueries") or [seed.get("name", "")]
    out: list[str] = []
    for value in values:
        value = str(value or "").strip()
        if value and value not in out:
            out.append(value)
    return out


def first_image(value) -> str:
    values = value if isinstance(value, list) else []
    if not values:
        return ""
    first = values[0]
    if isinstance(first, str):
        return first.replace("http://", "https://")
    if isinstance(first, dict):
        return str(first.get("imageUrl") or first.get("image_url") or "").replace("http://", "https://")
    return ""


def fetch_json(url: str, headers: dict[str, str]) -> dict:
    global _LAST_API_CALL
    req = urllib.request.Request(url, headers=headers)
    for attempt in range(4):
        elapsed = time.monotonic() - _LAST_API_CALL
        if elapsed < MIN_API_INTERVAL_SECONDS:
            time.sleep(MIN_API_INTERVAL_SECONDS - elapsed)
        try:
            _LAST_API_CALL = time.monotonic()
            with urllib.request.urlopen(req, timeout=15) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code not in (429, 500, 502, 503, 504) or attempt == 3:
                raise
            retry_after = exc.headers.get("Retry-After") if exc.headers else None
            try:
                delay = max(2.0, float(retry_after))
            except (TypeError, ValueError):
                delay = 2.5 + attempt * 2.5
            time.sleep(delay)
        except (urllib.error.URLError, TimeoutError):
            if attempt == 3:
                raise
            time.sleep(2.0 + attempt * 2.0)
    return {}



def fetch_text(url: str) -> str:
    req = urllib.request.Request(
        url,
        headers={**HEADERS, "Accept": "text/html,application/xhtml+xml"},
    )
    last = None
    for attempt in range(2):
        try:
            with urllib.request.urlopen(req, timeout=12) as response:
                raw = response.read()
            match = re.search(br'charset\s*=\s*["\']?([\w-]+)', raw[:10000], re.I)
            encoding = match.group(1).decode() if match else "utf-8"
            return raw.decode(encoding, errors="replace")
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
            last = exc
            if attempt == 0:
                time.sleep(0.8)
    raise last


def exact_page_info(item_url: str) -> dict | None:
    """Resolve live Rakuten itemId/price from the manually audited exact URL.

    This avoids relying on keyword search for listings that are live but poorly
    indexed inside a shop. Failure is non-fatal; caller falls back to shop search.
    """
    canonical = canonical_item_url(item_url)
    if not canonical:
        return None
    page = fetch_text(canonical)
    marker = '"itemInfoSku":'
    if marker not in page:
        return None
    try:
        info, _ = json.JSONDecoder().raw_decode(page.split(marker, 1)[1])
    except Exception:
        return None
    if info.get("sellType") not in (None, "NORMAL"):
        return None
    purchase = info.get("purchaseInfo", {}).get("purchaseBySellType", {})
    if purchase.get("purchaseCondition") not in (None, "enabled"):
        return None
    item_id = info.get("itemId")
    if not isinstance(item_id, int):
        return None
    price = purchase.get("normalPurchase", {}).get("price", {}).get("minPrice")
    return {"itemId": item_id, "price": int(price) if isinstance(price, (int, float)) else None}


def safe_affiliate(affiliate_url: str, item_url: str) -> bool:
    try:
        parsed = urllib.parse.urlparse(str(affiliate_url or ""))
        return (
            parsed.scheme == "https"
            and parsed.hostname == "hb.afl.rakuten.co.jp"
            and canonical_item_url(affiliate_url) == canonical_item_url(item_url)
        )
    except Exception:
        return False


def normalize_item(raw: dict) -> dict | None:
    item = raw.get("Item", raw) if isinstance(raw, dict) else None
    if not isinstance(item, dict):
        return None
    item_url = canonical_item_url(item.get("itemUrl", ""))
    affiliate_url = str(item.get("affiliateUrl") or "")
    try:
        price = int(item.get("itemPrice") or 0)
    except (TypeError, ValueError):
        price = 0
    image = first_image(item.get("mediumImageUrls"))
    if not item_url or price <= 0 or not image or not affiliate_url:
        return None
    if not safe_affiliate(affiliate_url, item_url):
        return None
    return {
        "name": str(item.get("itemName") or ""),
        "price": price,
        "itemUrl": item_url,
        "affiliateUrl": affiliate_url,
        "image": image,
        "itemCode": str(item.get("itemCode") or ""),
        "shopCode": str(item.get("shopCode") or ""),
    }


def fetch_exact_seed_item(seed: dict, env: dict[str, str]) -> dict | None:
    expected = canonical_item_url(seed.get("itemUrl", ""))
    expected_shop = rakuten_shop(expected)
    if not expected or not expected_shop:
        return None

    try:
        page_info = exact_page_info(expected)
    except Exception:
        return None
    if not page_info:
        return None

    params = {
        "applicationId": env["RAKUTEN_APPLICATION_ID"],
        "affiliateId": env["RAKUTEN_AFFILIATE_ID"],
        "itemCode": f"{expected_shop}:{page_info['itemId']}",
        "hits": 1,
        "format": "json",
        "formatVersion": 2,
        "availability": 1,
        "elements": (
            "itemName,itemCode,itemPrice,itemUrl,affiliateUrl,"
            "mediumImageUrls,availability,shopCode"
        ),
    }
    headers = {**HEADERS, "accessKey": env["RAKUTEN_ACCESS_KEY"]}
    payload = fetch_json(RAKUTEN_API + "?" + urllib.parse.urlencode(params), headers)
    source = payload.get("items") or payload.get("Items") or []
    for raw in source:
        candidate = normalize_item(raw)
        if not candidate:
            continue
        if candidate["itemUrl"] != expected:
            continue
        if not identity_ok(candidate["name"], seed):
            continue
        return candidate
    return None


def search_shop(seed: dict, env: dict[str, str]) -> dict | None:
    expected = canonical_item_url(seed["itemUrl"])
    expected_shop = rakuten_shop(expected)
    if not expected or not expected_shop:
        return None

    headers = {**HEADERS, "accessKey": env["RAKUTEN_ACCESS_KEY"]}
    matches: list[tuple[int, dict]] = []

    for query in seed_queries(seed):
        params = {
            "applicationId": env["RAKUTEN_APPLICATION_ID"],
            "affiliateId": env["RAKUTEN_AFFILIATE_ID"],
            "shopCode": expected_shop,
            "keyword": query,
            "hits": 30,
            "format": "json",
            "formatVersion": 2,
            "availability": 1,
            "field": 0,
            "elements": (
                "itemName,itemCode,itemPrice,itemUrl,affiliateUrl,"
                "mediumImageUrls,availability,shopCode"
            ),
        }
        payload = fetch_json(RAKUTEN_API + "?" + urllib.parse.urlencode(params), headers)
        source = payload.get("items") or payload.get("Items") or []
        for raw in source:
            candidate = normalize_item(raw)
            if not candidate:
                continue
            if candidate["shopCode"] and candidate["shopCode"] != expected_shop:
                continue
            if rakuten_shop(candidate["itemUrl"]) != expected_shop:
                continue
            if not identity_ok(candidate["name"], seed):
                continue
            level = 2 if candidate["itemUrl"] == expected else 1
            matches.append((level, candidate))

        if any(level == 2 for level, _ in matches):
            break

    if not matches:
        return None
    matches.sort(key=lambda pair: (-pair[0], pair[1]["price"]))
    return matches[0][1]


def load_seeds(seed_dir: Path) -> list[dict]:
    return [json.loads(path.read_text()) for path in sorted(seed_dir.glob("*.json"))]


def export_catalog(seed_dir: Path = DEFAULT_SEED_DIR) -> dict:
    env = {
        key: os.environ.get(key, "").strip()
        for key in ("RAKUTEN_APPLICATION_ID", "RAKUTEN_ACCESS_KEY", "RAKUTEN_AFFILIATE_ID")
    }
    missing = [key for key, value in env.items() if not value]
    if missing:
        raise RuntimeError("missing Rakuten credentials: " + ",".join(missing))
    if not seed_dir.exists():
        raise RuntimeError(f"seed directory not found: {seed_dir}")

    now = datetime.now(timezone.utc).isoformat()
    products: list[dict] = []
    failures: dict[str, str] = {}

    for seed in load_seeds(seed_dir):
        pid = seed.get("productId", "unknown")
        try:
            candidate = fetch_exact_seed_item(seed, env)
            audit_mode = "rakuten_api_exact_item_code"
            if candidate is None:
                candidate = search_shop(seed, env)
                audit_mode = "rakuten_api_same_shop_identity"
            if candidate is None:
                raise ValueError("same_shop_identity_listing_not_found")
            products.append({
                "productId": seed["productId"],
                "name": candidate["name"],
                "brand": seed.get("brand", ""),
                "categoryId": seed["categoryId"],
                "methodIds": seed.get("methodIds", []),
                "budgetTiers": seed.get("budgetTiers", []),
                "audiences": seed.get("audiences", []),
                "preferenceTags": seed.get("preferenceTags", []),
                "coverCategoryIds": seed.get("coverCategoryIds", [seed["categoryId"]]),
                "recommendationRole": seed.get("recommendationRole", "beginner_default"),
                "score": seed.get("score", 80),
                "price": candidate["price"],
                "itemCode": candidate["itemCode"],
                "itemUrl": candidate["itemUrl"],
                "affiliateUrl": candidate["affiliateUrl"],
                "image": candidate["image"],
                "verifiedAt": now,
                "specVerifiedAt": seed.get("specCheckedAt"),
                "audit": {
                    "status": "verified_live",
                    "mode": audit_mode,
                    "salesSource": "daily-cost-jp_github_actions",
                    "specEvidence": seed.get("specEvidenceUrl", ""),
                    "seedItemUrl": canonical_item_url(seed["itemUrl"]),
                },
            })
        except Exception as exc:
            failures[pid] = str(exc) if isinstance(exc, ValueError) else type(exc).__name__
        time.sleep(0.15)

    products.sort(key=lambda p: p["productId"])
    return {
        "version": 1,
        "updatedAt": now,
        "status": "ok" if not failures else "partial",
        "products": products,
        "failures": dict(sorted(failures.items())),
    }


def main() -> None:
    payload = export_catalog()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    tmp.replace(OUT)
    print(
        "SOTOJITAKU FISHING export:",
        payload["status"],
        "verified:", len(payload["products"]),
        "failed:", len(payload["failures"]),
    )
    for pid, reason in payload["failures"].items():
        print("FAIL", pid, reason)


if __name__ == "__main__":
    main()
