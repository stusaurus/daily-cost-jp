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
from datetime import datetime, timezone
from pathlib import Path

from export_sotojitaku_fishing import (
    canonical_item_url,
    exact_item_candidate,
    identity_ok,
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

            candidate=exact_item_candidate(seed,env)
            lookup_mode="rakuten_api_exact_item_code"
            if candidate is None:
                candidate,lookup_mode=search_identity(seed,env)
            if candidate is None:
                raise ValueError("live_identity_listing_not_found")
            if not identity_ok(candidate.get("name",""),seed):
                raise ValueError("identity_mismatch")

            resolved=canonical_item_url(candidate.get("itemUrl",""))
            resolved_shop=candidate.get("shopCode") or rakuten_shop(resolved)
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
        "auditPolicyVersion":"carstay-daily-cost-rakuten-api-v1",
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
