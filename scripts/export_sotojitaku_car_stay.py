#!/usr/bin/env python3
"""Export a verified SOTOJITAKU CAR STAY Rakuten catalog.

This runs in daily-cost-jp because this repository already owns the Rakuten API
credentials. Vehicle-fit intent remains authoritative in SOTOJITAKU; this script
only resolves current same-shop Rakuten listings, price/image and affiliate URLs.

The exporter is fail-closed:
- exact audited URL is preferred
- fallback listing must remain in the same audited Rakuten shop
- every identity group must match and forbidden terms must not
- affiliate URL must target the exact resolved item URL
- vehicleFit / gapIds are copied unchanged from SOTOJITAKU
"""
from __future__ import annotations

import json
import os
import time
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

from export_sotojitaku_fishing import (
    HEADERS,
    RAKUTEN_API,
    canonical_item_url,
    exact_item_candidate,
    fetch_json,
    identity_ok,
    normalize_item,
    rakuten_shop,
    search_identity,
)

ROOT=Path(__file__).resolve().parents[1]
DEFAULT_SEED_DIR=Path(os.environ.get(
    "CAR_STAY_SEED_DIR",
    "/tmp/sotojitaku/car-stay/data/product-seeds",
))
OUT=Path(os.environ.get(
    "CAR_STAY_EXPORT_OUT",
    str(ROOT/"shared-data"/"sotojitaku-car-stay-products.json"),
))


def candidate_seed(seed:dict)->dict:
    """Use relaxed title identity only when a seed explicitly defines it.

    Fit dimensions remain authoritative in SOTOJITAKU and are exported unchanged.
    This only avoids requiring audited dimensions to appear in Rakuten's item title.
    """
    groups=seed.get("candidateIdentityGroups")
    if not groups:
        return seed
    adjusted=dict(seed)
    adjusted["identityGroups"]=groups
    return adjusted

def explicit_item_code_candidate(seed:dict,env:dict[str,str])->dict|None:
    """Resolve the manually curated Rakuten itemCode without scraping the sales page."""
    item_code=str(seed.get("rakutenItemCode") or "").strip()
    expected=canonical_item_url(seed.get("itemUrl",""))
    if not item_code or not expected:
        return None
    params={
        "applicationId":env["RAKUTEN_APPLICATION_ID"],
        "affiliateId":env["RAKUTEN_AFFILIATE_ID"],
        "itemCode":item_code,
        "hits":1,
        "format":"json",
        "formatVersion":2,
        "availability":1,
        "elements":"itemName,itemCode,itemPrice,itemUrl,affiliateUrl,mediumImageUrls,availability,shopCode",
    }
    headers={**HEADERS,"accessKey":env["RAKUTEN_ACCESS_KEY"]}
    payload=fetch_json(RAKUTEN_API+"?"+urllib.parse.urlencode(params),headers)
    source=payload.get("items") or payload.get("Items") or []
    for raw in source:
        candidate=normalize_item(raw)
        if not candidate:
            continue
        if candidate["itemUrl"]!=expected:
            continue
        if not identity_ok(candidate["name"],candidate_seed(seed)):
            continue
        return candidate
    return None

def resolve_candidate(seed:dict,env:dict[str,str])->tuple[dict|None,str,list[str]]:
    """Try each live-listing resolver independently.

    A stale/manual seller code may legitimately return a Rakuten HTTP error even when
    the exact audited product page is still live. One resolver failure must therefore
    not suppress the safer exact-page itemId or identity-search fallbacks.
    """
    errors=[]
    try:
        candidate=explicit_item_code_candidate(seed,env)
        if candidate is not None:
            return candidate,"rakuten_api_seed_item_code",errors
    except Exception as exc:
        errors.append("seed_item_code:"+type(exc).__name__)

    try:
        candidate=exact_item_candidate(candidate_seed(seed),env)
        if candidate is not None:
            return candidate,"rakuten_api_exact_page_item",errors
    except Exception as exc:
        errors.append("exact_page_item:"+type(exc).__name__)

    try:
        candidate,mode=search_identity(candidate_seed(seed),env)
        if candidate is not None:
            return candidate,mode,errors
    except Exception as exc:
        errors.append("identity_search:"+type(exc).__name__)

    return None,"none",errors

def load_seeds(seed_dir:Path)->list[dict]:
    return [json.loads(path.read_text()) for path in sorted(seed_dir.glob("*.json"))]

def export_catalog(seed_dir:Path=DEFAULT_SEED_DIR)->dict:
    env={
        key:os.environ.get(key,"").strip()
        for key in ("RAKUTEN_APPLICATION_ID","RAKUTEN_ACCESS_KEY","RAKUTEN_AFFILIATE_ID")
    }
    missing=[key for key,value in env.items() if not value]
    if missing:
        raise RuntimeError("missing Rakuten credentials: "+",".join(missing))
    if not seed_dir.exists():
        raise RuntimeError(f"seed directory not found: {seed_dir}")

    now=datetime.now(timezone.utc).isoformat()
    products=[]
    failures={}
    seeds=load_seeds(seed_dir)

    for seed in seeds:
        pid=seed.get("productId","unknown")
        try:
            expected=canonical_item_url(seed.get("itemUrl",""))
            expected_shop=rakuten_shop(expected)
            if not expected or not expected_shop:
                raise ValueError("seed_item_url_invalid")

            candidate,lookup_mode,source_errors=resolve_candidate(seed,env)
            if candidate is None:
                suffix=(" ["+",".join(source_errors)+"]") if source_errors else ""
                raise ValueError("live_identity_listing_not_found"+suffix)
            if not identity_ok(candidate.get("name",""),candidate_seed(seed)):
                raise ValueError("identity_mismatch")

            resolved=canonical_item_url(candidate.get("itemUrl",""))
            resolved_shop=rakuten_shop(resolved)
            candidate_shop=str(candidate.get("shopCode") or "").strip()
            if candidate_shop and candidate_shop!=resolved_shop:
                raise ValueError("candidate_shop_url_mismatch")
            if not resolved or resolved_shop!=expected_shop:
                raise ValueError("cross_shop_rejected")

            fit_checked=seed.get("fitCheckedAt")
            if not fit_checked:
                raise ValueError("fit_audit_missing")

            products.append({
                "productId":seed["productId"],
                "name":candidate["name"],
                "brand":seed.get("brand",""),
                "gapIds":seed.get("gapIds",[]),
                "recommendationRole":seed.get("recommendationRole","beginner_default"),
                "score":seed.get("score",80),
                "price":candidate["price"],
                "itemCode":candidate.get("itemCode",""),
                "itemUrl":resolved,
                "affiliateUrl":candidate["affiliateUrl"],
                "image":candidate["image"],
                "verifiedAt":now,
                "fitVerifiedAt":fit_checked,
                "fitStrategy":seed.get("fitStrategy","vehicle"),
                "measurementFit":seed.get("measurementFit"),
                "vehicleFit":seed.get("vehicleFit",[]),
                "audit":{
                    "status":"verified_live",
                    "mode":lookup_mode,
                    "salesSource":"daily-cost-jp_github_actions",
                    "fitEvidence":seed.get("fitEvidenceUrl",""),
                    "seedItemUrl":expected,
                },
            })
        except Exception as exc:
            failures[pid]=str(exc) if isinstance(exc,ValueError) else type(exc).__name__
        time.sleep(0.15)

    products.sort(key=lambda p:p["productId"])
    return {
        "version":1,
        "updatedAt":now,
        "auditPolicyVersion":"carstay-daily-cost-rakuten-api-v2",
        "status":"ok" if not failures else "partial",
        "seedCount":len(seeds),
        "verifiedCount":len(products),
        "products":products,
        "failures":dict(sorted(failures.items())),
        "deferred":{},
        "runtimeBudgetSeconds":0,
    }

def main()->None:
    payload=export_catalog()
    OUT.parent.mkdir(parents=True,exist_ok=True)
    tmp=OUT.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n")
    tmp.replace(OUT)
    print(
        "SOTOJITAKU CAR STAY export:",
        payload["status"],
        "verified:",len(payload["products"]),
        "failed:",len(payload["failures"]),
    )
    for pid,reason in payload["failures"].items():
        print("FAIL",pid,reason)

if __name__=="__main__":
    main()
