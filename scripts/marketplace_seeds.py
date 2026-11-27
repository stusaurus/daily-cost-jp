"""Find additional in-stock retail listings using the official product directory."""
from collections import Counter, defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo
from http.client import HTTPException
import time
from urllib.error import HTTPError, URLError

from marketplace_discovery import UNKNOWN_PACK, UNSAFE, source_evidence
from marketplace_offers import AMBIGUOUS, explicit_jans, known_shipping, valid_jan
from product_quality import category_rejection, filter_items
from sale_quantity import normalize
from yahoo_shopping import YahooUnavailable

# Spread the acquisition budget across categories, including categories with few reviews.
HISTORY_DAYS = 3
RECOVERY_DAYS = 7
RECOVERY_PER_CATEGORY = 3
SEEDS_PER_CATEGORY = 20
YAHOO_SEEDS_PER_CATEGORY = 8
FIELDS = "itemName,itemCaption,itemCode,itemPrice,shopName,affiliateUrl,availability,postageFlag,reviewCount"


# Product names used in the directory omit seller packaging and shipping language.
# Retail searches target configurations that households can actually order.
DISCOVERY_QUERIES = {
    "tissue": (("箱 ティシュー", "スコッティ ティシュー", "ネピア ティシュ"),
               ("ティシュー 5箱 200組", "ボックスティッシュ 5箱", "ティシュー 3箱 200組")),
    "coffee": (("レギュラーコーヒー 粉", "レギュラーコーヒー 豆", "職人の珈琲 粉"),
               ("レギュラーコーヒー 粉 まとめ買い", "珈琲 豆 500g", "職人の珈琲 粉 280g")),
    "toothbrush": (("手用 ハブラシ", "クリニカ ハブラシ", "システマ ハブラシ", "歯ブラシ コンパクト"),
                   ("ハブラシ コンパクト ふつう 1本", "歯ブラシ ふつう 3本", "ハブラシ コンパクト やわらかめ")),
    "kitchen-paper": (("キッチンタオル", "クッキングペーパー", "キッチンペーパー"),
                      ("キッチンタオル 2ロール 100カット", "キッチンタオル 4ロール 50カット", "キッチンペーパー シート")),
    "sink-net": (("水切りネット", "排水口 水切り ストッキング", "三角コーナー 水切りネット"),
                 ("排水口 水切りネット 50枚", "排水口 ストッキング 水切りネット", "浅型 水切りネット 30枚")),
    "toilet-paper": (("トイレットロール", "トイレットペーパー"), ("トイレットペーパー ダブル 12ロール", "トイレットペーパー シングル 12ロール")),
    "water": (("ミネラルウォーター", "天然水"), ("天然水 2L 6本", "ミネラルウォーター 500ml 24本")),
    "paper-towel": (("ペーパータオル", "ハンドタオル ペーパー"), ("ペーパータオル 200枚", "ペーパータオル 小判 200枚")),
    "garbage-bag-45l": (("ごみ袋 45L", "ポリ袋 45L"), ("ごみ袋 45L 30枚", "ポリ袋 45L 半透明 100枚")),
    "mask": (("不織布 マスク", "プリーツ 不織布マスク"), ("不織布マスク ふつう 30枚", "不織布マスク 小さめ 50枚")),
    "cotton-swab": (("紙軸 綿棒", "抗菌 綿棒"), ("紙軸 綿棒 200本", "ベビー 綿棒 紙軸")),
    "wet-wipes": (("除菌 ウェットティッシュ", "除菌 ウェットシート"), ("除菌 ウェットティッシュ 詰め替え 80枚", "ノンアルコール 除菌 ウェットティッシュ")),
}
PRIORITY_SEARCH = {"tissue", "coffee", "toothbrush", "kitchen-paper", "sink-net"}


def retail_query(category, day):
    queries = DISCOVERY_QUERIES[category][1]
    return queries[day % len(queries)]


def directory_products(payload):
    rows = payload.get("Products", payload.get("items"))
    if rows is None and payload.get("count") in (0, "0"):
        return []
    if not isinstance(rows, list):
        raise ValueError("product_directory_schema")
    return [row.get("Product", row) for row in rows if isinstance(row, dict)]


def ranked_seeds(raw, excluded):
    by_jan = {}
    for product in raw:
        if not isinstance(product, dict):
            continue
        jan = str(product.get("productCode") or "")
        name = product.get("productName")
        if (len(jan) != 13 or not valid_jan(jan) or jan in excluded or not isinstance(name, str)
                or not name.strip() or not product.get("salesItemCount")):
            continue
        by_jan[jan] = {"jan": jan, "name": name, "brand": str(product.get("brandName") or ""),
                       "maker": str(product.get("makerName") or ""),
                       "sellers": int(product["salesItemCount"]), "reviews": int(product.get("reviewCount") or 0)}
    return sorted(by_jan.values(), key=lambda seed: (-seed["reviews"], -seed["sellers"], seed["jan"]))


def select_seeds(seeds, previous, limit, day, recent=None):
    """Refresh confirmed JANs first and rotate a bounded slice of the other candidates."""
    by_jan = {seed["jan"]: seed for seed in seeds}
    kept = [by_jan.get(jan, {"jan": jan, "name": "", "brand": ""})
            for jan in sorted(previous) if valid_jan(jan)][:24]
    remaining = [seed for seed in seeds if seed["jan"] not in previous]
    available = min(24 - len(kept), max(3, limit - len(kept)))
    if len(remaining) > available:
        fixed = available // 2
        rotating = remaining[fixed:]
        offset = day * (available - fixed) % len(rotating)
        remaining = remaining[:fixed] + rotating[offset:] + rotating[:offset]
    if recent:
        remaining.sort(key=lambda seed: recent.get(seed["jan"], 0))
    return kept + remaining[:available]


def yahoo_leads(category, hits, affiliate_link):
    """Return eligible seller listings keyed by GTIN. Their titles are never master data."""
    grouped = defaultdict(list)
    for hit in hits:
        jan, title = hit.get("janCode"), hit.get("name")
        terms = normalize(" ".join(str(hit.get(key) or "") for key in ("name", "headLine", "description")))
        shipping, label = hit.get("shipping"), hit.get("priceLabel")
        if (not valid_jan(jan) or len(jan) != 13 or len(set(jan)) <= 1
                or not isinstance(title, str) or category_rejection(category, title)
                or explicit_jans(title) - {jan} or UNSAFE.search(terms) or AMBIGUOUS.search(normalize(title))
                or UNKNOWN_PACK.search(normalize(title)) or not known_shipping(terms)
                or hit.get("inStock") is not True or hit.get("condition") != "new"
                or not isinstance(shipping, dict) or shipping.get("code") != 2
                or not isinstance(label, dict) or label.get("taxable") is not True
                or type(hit.get("price")) is not int or hit["price"] <= 0 or not affiliate_link(hit)):
            continue
        grouped[jan].append(hit)
    return dict(grouped)


def collect_yahoo_leads(categories, client, day):
    from candidate_acquisition import SUPPLEMENTAL_QUERIES
    leads, stats = {}, {"categories": {}, "requests": 0}
    before = client.requests
    for category, config in categories.items():
        queries = DISCOVERY_QUERIES[category][1] if category in DISCOVERY_QUERIES else tuple(
            dict.fromkeys((config["keyword"], *SUPPLEMENTAL_QUERIES.get(category, ()))))
        try:
            hits = client.search(query=queries[day % len(queries)], shipping="free")
        except YahooUnavailable as error:
            stats["categories"][category] = {"error": str(error)}
            break
        leads[category] = yahoo_leads(category, hits, client.affiliate_link)
        stats["categories"][category] = {"hits": len(hits), "eligible_jans": len(leads[category])}
    stats["requests"] = client.requests - before
    return leads, stats


def bounded_days(values, day, window):
    if not isinstance(values, dict):
        return {}
    return {jan: stamp for jan, stamp in values.items()
            if valid_jan(jan) and type(stamp) is int and day - window < stamp <= day}


def history_stats(include, history, confirmed, day):
    """Carry only bounded JAN/date evidence even when no API lookup can run."""
    return {"product_searches": 0, "item_searches": 0, "categories": {
        category: {"status": "not_processed", "seeds": 0, "queried": 0,
                   "verified_rows": 0, "reasons": Counter(),
                   "lookup_days": bounded_days((history or {}).get(category), day, HISTORY_DAYS),
                   "prior_match_days": bounded_days((confirmed or {}).get(category), day, RECOVERY_DAYS)}
        for category in include}}


def extend_pool(pool, include, *, directory, listings, normalize_item, categories, pause=time.sleep,
                per_category=SEEDS_PER_CATEGORY, previous=None, day=0, keyword_hits=None, coverage=None, history=None, confirmed=None, retail=None):
    stats = history_stats(include, history, confirmed, day)
    for category, profiles in include.items():
        config = categories[category]
        info = stats["categories"][category]
        info.pop("status")
        recent = dict(info["lookup_days"])
        confirmed_days = info["prior_match_days"]
        verified = []
        try:
            pause(1.2)
            stats["product_searches"] += 1
            targeted = (coverage or {}).get(category, 0) < 5 and category in DISCOVERY_QUERIES
            master = DISCOVERY_QUERIES[category][0] if targeted else ()
            primary = {**config, "name": master[0]} if master else config
            try:
                raw = directory(primary, 1)
            except ValueError:
                # A missing directory envelope does not invalidate independent Yahoo leads.
                if not (keyword_hits or {}).get(category):
                    raise
                info["directory_error"] = "invalid_response"
                raw = []
            if category in (coverage or {}) and coverage[category] < 5:
                from candidate_acquisition import SUPPLEMENTAL_QUERIES
                alternatives = master[1:] if master else SUPPLEMENTAL_QUERIES.get(category, ())
                if alternatives:
                    pause(1.2)
                    stats["product_searches"] += 1
                    query = alternatives[day % len(alternatives)]
                    try:
                        raw = raw + directory({**config, "name": query}, 1)
                    except ValueError:
                        info["alternate_directory_error"] = "invalid_response"
            seeds = ranked_seeds(raw, {profile.jan for profile in profiles})
            info["seeds"] = len(seeds)
            historical = set((previous or {}).get(category, ())) - {profile.jan for profile in profiles}
            # A temporarily missing offer can return on a later day. Recheck only its JAN,
            # against both live APIs, within the normal listing budget.
            recoverable = sorted((jan for jan in confirmed_days if jan not in historical
                                  and jan not in {profile.jan for profile in profiles} and recent.get(jan) != day),
                                 key=lambda jan: (-confirmed_days[jan], jan))
            recovery = recoverable[:min(RECOVERY_PER_CATEGORY, max(0, per_category - len(historical) - 3))]
            selected = select_seeds(seeds, historical | set(recovery), per_category, day, recent)
            info["recovery_lookups"] = len(recovery)
            excluded = {profile.jan for profile in profiles} | {seed["jan"] for seed in selected}
            directory_by_jan = {seed["jan"]: seed for seed in seeds}
            additional = [jan for jan in (keyword_hits or {}).get(category, {}) if jan not in excluded]
            additional.sort(key=lambda jan: recent.get(jan, 0))
            for jan in additional[:YAHOO_SEEDS_PER_CATEGORY]:
                selected.append(directory_by_jan.get(jan, {"jan": jan, "name": "", "brand": ""}))
            info["yahoo_only_lookups"] = min(len(additional), YAHOO_SEEDS_PER_CATEGORY)
            protected = historical | set(recovery) | (keyword_hits or {}).get(category, {}).keys()
            requests = [(seed["jan"], seed) for seed in selected]
            if retail and targeted and category in PRIORITY_SEARCH:
                # Replace only a speculative directory JAN. Keep every
                # previous winner, recovery candidate and two-market lead.
                for index in range(len(selected) - 1, -1, -1):
                    if selected[index]["jan"] not in protected:
                        requests[index] = (retail_query(category, day), None)
                        break
            for query, seed in requests:
                pause(1.2)
                stats["item_searches"] += 1
                info["queried"] += 1
                if seed is None:
                    info["retail_keyword_searches"] = 1
                    fresh = retail(query)
                    info["retail_keyword_hits"] = len(fresh)
                else:
                    fresh = listings(query)
                    info["lookup_days"][query] = day
                    if not fresh:
                        info["reasons"]["empty_jan_lookup"] += 1
                info["listing_rows"] = info.get("listing_rows", 0) + len(fresh)
                for raw_item in fresh:
                    source = raw_item.get("Item", raw_item)
                    row = normalize_item(raw_item, config)
                    proof = source_evidence(source, row)
                    if not proof:
                        info["reasons"]["unverified_listing"] += 1
                        continue
                    jan = proof["jan"]
                    if seed and jan != query:
                        info["reasons"]["different_jan"] += 1
                        continue
                    metadata = seed or directory_by_jan.get(jan, {})
                    verified.append({**row, **proof, "master_name": metadata.get("name", ""),
                                     "prior_match": jan in historical, "retail_keyword": seed is None,
                                     "master_brand": metadata.get("brand", ""), "master_maker": metadata.get("maker", "")})
        except (HTTPError, HTTPException, OSError, URLError, TypeError, ValueError, KeyError, AttributeError) as error:
            info["error"] = f"http_{error.code}" if isinstance(error, HTTPError) else type(error).__name__
            # Stop on provider throttling/authentication failures. A malformed
            # category result or one transient outage need not starve later categories.
            if (isinstance(error, HTTPError) and error.code in (401, 403, 429)
                    or sum("error" in item for item in stats["categories"].values()) >= 3):
                stats["stopped"] = info["error"]
        quality_report = {}
        accepted = filter_items(category, verified, quality_report)
        info["catalog_exclusions"] = quality_report[category]["reasons"]
        info["verified_rows"] = len(accepted)
        info["retail_keyword_verified"] = sum(row["retail_keyword"] for row in accepted)
        info["reasons"]["catalog_quality"] += len(verified) - len(accepted)
        # The fresh JAN request wins when the reviewed category query returned the same item.
        rows = {row["item_code"]: row for row in pool.get(category, [])}
        rows.update((row["item_code"], row) for row in accepted)
        pool[category] = list(rows.values())
        if "stopped" in stats:
            break
    return stats


def read_prior_state():
    # Prior publication supplies lookup keys only. All prices, stock, terms, titles
    # and affiliate destinations still come from this build's API responses.
    from price_observations import fetch_public
    previous, coverage, history, confirmed = {}, {}, {}, {}
    try:
        last_build = fetch_public("marketplace-coverage.json")
        entries = last_build["categories"]
        for key, entry in entries.items():
            if type(entry.get("comparable")) is int:
                coverage[key] = entry["comparable"]
            previous[key] = {row["jan"] for row in entry.get("discovery", {}).get("sources", [])
                             if valid_jan(row.get("jan"))}
        stamp = datetime.fromisoformat(last_build["catalog_updated_at"]).astimezone(ZoneInfo("Asia/Tokyo")).date().toordinal()
        directory_stats = last_build.get("api", {}).get("directory", {}).get("categories", {})
        for key, winners in previous.items():
            prior = directory_stats.get(key, {}).get("prior_match_days", {})
            confirmed[key] = dict(prior) if isinstance(prior, dict) else {}
            confirmed[key].update(dict.fromkeys(winners, stamp))
        history = {key: value["lookup_days"] for key, value in directory_stats.items()
                   if isinstance(value.get("lookup_days"), dict)}
    except (OSError, HTTPException, TypeError, KeyError, ValueError, AttributeError):
        previous, coverage, history, confirmed = {}, {}, {}, {}
    return previous, coverage, history, confirmed


def preserve_directory_history(include, now):
    """Do not recover stale offers when directory acquisition was skipped."""
    _, _, history, confirmed = read_prior_state()
    day = now.astimezone(ZoneInfo("Asia/Tokyo")).date().toordinal()
    return history_stats(include, history, confirmed, day)


def extend_current(pool, include, client):
    from build_site_entry import core, fetch_search_items, normalize_item_with_correct_postage
    from build_site_products import PRODUCT_API_URL
    from rakuten_request import fetch_json
    from urllib.parse import urlencode
    from urllib.request import Request
    def directory(config, page):
        params = {"applicationId": core.APP_ID, "keyword": config["name"].split("（")[0], "page": page,
                  "hits": 30, "formatVersion": 2, "format": "json",
                  "elements": "productCode,productName,brandName,makerName,salesItemCount,reviewCount"}
        req = Request(PRODUCT_API_URL + "?" + urlencode(params),
                      headers={"accessKey": core.ACCESS_KEY, "Origin": "https://stusaurus.github.io",
                               "Referer": core.SITE_URL, "User-Agent": "daily-cost-jp/0.8"})
        return directory_products(fetch_json(req))

    def listings(keyword, *, sort="+itemPrice"):
        return fetch_search_items({
            "applicationId": core.APP_ID, "affiliateId": core.AFFILIATE_ID,
            "keyword": keyword, "availability": 1, "postageFlag": 1,
            "sort": sort, "hits": 30, "formatVersion": 2, "format": "json", "elements": FIELDS,
        })
    previous, coverage, history, confirmed = read_prior_state()
    day = datetime.now(ZoneInfo("Asia/Tokyo")).date().toordinal()
    categories = {item["id"]: item for item in core.CATEGORIES if item["id"] in include}
    keyword_hits, keyword_stats = collect_yahoo_leads(categories, client, day)
    stats = extend_pool(pool, include, directory=directory, listings=listings,
                        previous=previous, day=day, keyword_hits=keyword_hits, coverage=coverage,
                        history=history, confirmed=confirmed, retail=lambda query: listings(query, sort="-reviewCount"),
                        normalize_item=normalize_item_with_correct_postage, categories=categories)
    stats["yahoo_leads"] = keyword_stats
    return stats, keyword_hits
