"""Build a verified SOTOJITAKU FISHING product catalog during daily-cost-jp Pages builds.

The daily-cost-jp repository already has Rakuten Web Service credentials in GitHub
Actions. This script reads the public FISHING product seeds from sotojitaku, finds a
currently purchasable item in the manually audited Rakuten shop, verifies the seed's
identity groups, and writes affiliate-enabled product data into the Pages artifact.

No credentials are written to the output.
"""
from __future__ import annotations

import concurrent.futures
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

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"site"/"shared"/"fishing-products.json"
SEEDS_API="https://api.github.com/repos/stusaurus/sotojitaku/contents/fishing/data/product-seeds?ref=main"
RAKUTEN_API="https://openapi.rakuten.co.jp/ichibams/api/IchibaItem/Search/20260701"
UA="daily-cost-jp-fishing-catalog/1.0"


def fetch_json(url,headers=None,timeout=18):
    req=urllib.request.Request(url,headers={"User-Agent":UA,**(headers or {})})
    last=None
    for attempt in range(2):
        try:
            with urllib.request.urlopen(req,timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except (urllib.error.HTTPError,urllib.error.URLError,TimeoutError) as exc:
            last=exc
            if attempt==0: time.sleep(1)
    raise last


def compact(value):
    return re.sub(r"\s+","",unicodedata.normalize("NFKC",str(value or ""))).lower()


def canonical_item_url(value):
    try:
        u=urllib.parse.urlparse(str(value or ""))
        if u.hostname!="item.rakuten.co.jp": return ""
        path=re.sub(r"/+","/",u.path).rstrip("/")+"/"
        return f"https://item.rakuten.co.jp{path}"
    except Exception:
        return ""


def shop_code(value):
    u=urllib.parse.urlparse(canonical_item_url(value))
    parts=[p for p in u.path.split("/") if p]
    return parts[0] if parts else ""


def identity_ok(name,seed):
    n=compact(name)
    if any(compact(term) in n for term in seed.get("forbiddenTerms",[])):
        return False
    return all(any(compact(term) in n for term in group) for group in seed.get("identityGroups",[]))


def first_image(item):
    imgs=item.get("mediumImageUrls") or []
    if not imgs: return ""
    img=imgs[0]
    return str(img.get("imageUrl","") if isinstance(img,dict) else img)


def load_seeds():
    listing=fetch_json(SEEDS_API,timeout=20)
    urls=[x.get("download_url") for x in listing if x.get("type")=="file" and str(x.get("name","")).endswith(".json")]
    seeds=[]
    for url in urls:
        if not url: continue
        seeds.append(fetch_json(url,timeout=15))
    return seeds


def search_shop(seed,env):
    expected=canonical_item_url(seed["itemUrl"])
    shop=shop_code(expected)
    if not shop: raise ValueError("invalid_seed_shop")
    queries=[]
    for value in seed.get("searchQueries") or [seed.get("name","")]:
        value=str(value or "").strip()
        if value and value not in queries: queries.append(value)

    headers={"accessKey":env["RAKUTEN_ACCESS_KEY"]}
    matches=[]
    errors=[]
    for query in queries[:3]:
        params={
            "applicationId":env["RAKUTEN_APPLICATION_ID"],
            "affiliateId":env["RAKUTEN_AFFILIATE_ID"],
            "shopCode":shop,
            "keyword":query,
            "hits":30,
            "formatVersion":2,
            "availability":1,
            "field":0,
            "elements":"itemName,itemCode,itemPrice,itemUrl,affiliateUrl,mediumImageUrls,availability,shopCode",
        }
        try:
            payload=fetch_json(RAKUTEN_API+"?"+urllib.parse.urlencode(params),headers=headers,timeout=16)
        except Exception as exc:
            errors.append(type(exc).__name__)
            continue
        for raw in payload.get("items") or payload.get("Items") or []:
            item=raw.get("Item",raw)
            name=str(item.get("itemName") or "")
            url=canonical_item_url(item.get("itemUrl",""))
            if not url or shop_code(url)!=shop or not identity_ok(name,seed):
                continue
            affiliate=str(item.get("affiliateUrl") or "")
            price=item.get("itemPrice")
            image=first_image(item)
            if not affiliate.startswith("https://hb.afl.rakuten.co.jp/"): continue
            if not isinstance(price,(int,float)) or price<=0: continue
            if not image.startswith("https://"): continue
            level=2 if url==expected else 1
            matches.append((level,{
                "name":name,
                "price":int(price),
                "itemCode":str(item.get("itemCode") or ""),
                "itemUrl":url,
                "affiliateUrl":affiliate,
                "image":image,
            }))
        if any(level==2 for level,_ in matches): break

    if not matches:
        suffix=(" ["+",".join(errors)+"]") if errors else ""
        raise ValueError("same_shop_identity_listing_not_found"+suffix)
    matches.sort(key=lambda pair:(-pair[0],pair[1]["price"]))
    return matches[0]


def audit_one(seed,env,now):
    pid=seed.get("productId","unknown")
    try:
        level,item=search_shop(seed,env)
        product={
            "productId":seed["productId"],
            "name":item["name"],
            "brand":seed.get("brand",""),
            "categoryId":seed["categoryId"],
            "methodIds":seed.get("methodIds",[]),
            "budgetTiers":seed.get("budgetTiers",[]),
            "audiences":seed.get("audiences",[]),
            "preferenceTags":seed.get("preferenceTags",[]),
            "coverCategoryIds":seed.get("coverCategoryIds",[seed["categoryId"]]),
            "recommendationRole":seed.get("recommendationRole","beginner_default"),
            "score":seed.get("score",80),
            "price":item["price"],
            "itemCode":item["itemCode"],
            "itemUrl":item["itemUrl"],
            "affiliateUrl":item["affiliateUrl"],
            "image":item["image"],
            "verifiedAt":now,
            "specVerifiedAt":seed.get("specCheckedAt"),
            "audit":{
                "status":"verified_live",
                "mode":"exact_url" if level==2 else "same_shop_identity",
                "salesSource":"daily_cost_rakuten_api",
                "specEvidence":seed.get("specEvidenceUrl",""),
            },
        }
        return pid,product,None
    except Exception as exc:
        return pid,None,str(exc) if isinstance(exc,ValueError) else type(exc).__name__


def coverage(products):
    required={
        "sabiki":["rod_reel","rig","bait","life_jacket_adult","bucket","fish_grip","scissors"],
        "choi_nage":["rod_reel","rig","bait","life_jacket_adult","fish_grip","scissors","pliers"],
    }
    budgets=["low","balanced","long_term"]
    missing=[]
    def supports(method,budget,category):
        return any(
            method in p.get("methodIds",[]) and
            budget in p.get("budgetTiers",[]) and
            category in p.get("coverCategoryIds",[])
            for p in products
        )
    for method,categories in required.items():
        for budget in budgets:
            for category in categories:
                if not supports(method,budget,category):
                    missing.append(f"{method}/{budget}/{category}")
    if not any("life_jacket_child" in p.get("coverCategoryIds",[]) for p in products):
        missing.append("family_child/life_jacket_child")
    for budget in budgets:
        if not any("cooler" in p.get("coverCategoryIds",[]) and budget in p.get("budgetTiers",[]) for p in products):
            missing.append(f"take_home/{budget}/cooler")
    return missing


def main():
    env={k:os.environ.get(k,"").strip() for k in ("RAKUTEN_APPLICATION_ID","RAKUTEN_ACCESS_KEY","RAKUTEN_AFFILIATE_ID")}
    missing_env=[k for k,v in env.items() if not v]
    if missing_env: raise SystemExit("Missing Rakuten build credentials: "+",".join(missing_env))

    seeds=load_seeds()
    now=datetime.now(timezone.utc).isoformat()
    products=[]; failures={}
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
        futures=[ex.submit(audit_one,seed,env,now) for seed in seeds]
        for fut in concurrent.futures.as_completed(futures):
            pid,product,error=fut.result()
            if product: products.append(product)
            else: failures[pid]=error or "audit_failed"

    products.sort(key=lambda p:p["productId"])
    missing=coverage(products)
    payload={
        "version":1,
        "updatedAt":now,
        "status":"ok" if not failures and not missing else "partial",
        "products":products,
        "failures":dict(sorted(failures.items())),
        "coverage":{"ok":not missing,"missing":missing},
        "source":"daily-cost-jp-build",
    }
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n")
    print("FISHING shared catalog:",payload["status"],"verified:",len(products),"failed:",len(failures),"missing:",len(missing))


if __name__=="__main__":
    main()
