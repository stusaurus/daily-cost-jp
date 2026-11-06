"""Audit live affiliate CTA HTML without clicking, tracking or contacting merchants.

The sixth site (CAMP) is a client-rendered SPA: only its publicly served JS
markup contract can be verified without executing the app. Do not call that
an interactive link verification. No product names, URLs or IDs are stored.
"""
import json
from collections import Counter
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

ORIGIN = "https://stusaurus.github.io"
TARGETS = [
    ("daily", "/daily-cost-jp/categories/laundry/"),
    ("baby", "/baby-cost-jp/diapers/pants/m/"),
    ("food", "/food-cost-jp/categories/pack-rice/"),
    ("kyo-bodo", "/kyo-bodo-jp/scenes/two-player/"),
    ("pet", "/pet-cost-jp/categories/pet-sheets/"),
]
CAMP_PATH = "/sotojitaku/camp/app.js"
OUTPUT = Path("audit-results/six-site-affiliate-link-contract.json")


def is_candidate(site, attrs):
    if site == "daily":
        return any(x in attrs.get("class", "").split()
                   for x in ("buy-button", "size-link", "exact-rakuten"))
    if site == "pet":
        return "data-affiliate-link" in attrs
    return attrs.get("data-affiliate") == "rakuten"


def inspect_anchor(attrs):
    """Classify URL scheme, host and sponsored-link protections; never open it."""
    url = attrs.get("href") or ""
    try:
        parsed = urlsplit(str(url).strip())
        host = (parsed.hostname or "").lower()
    except ValueError:
        parsed = urlsplit("")
        host = ""
    rel = set(str(attrs.get("rel") or "").lower().split())
    problems = []
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        problems.append("INVALID_OR_NON_HTTPS_URL")
    if "sponsored" not in rel:
        problems.append("MISSING_SPONSORED_REL")
    if attrs.get("target") == "_blank" and "noopener" not in rel:
        problems.append("MISSING_NOOPENER")
    known_rakuten = host == "r10.to" or host == "rakuten.co.jp" or host.endswith(".rakuten.co.jp")
    return {"problems": problems, "host": host if host else "(none)",
            "externalHostNeedsReview": bool(host and not known_rakuten)}


class LinkParser(HTMLParser):
    def __init__(self, site):
        super().__init__(convert_charrefs=True)
        self.site = site
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag != "a":
            return
        attrs = dict(attrs)
        if is_candidate(self.site, attrs):
            self.links.append(inspect_anchor(attrs))


def audit_html(site, html):
    parser = LinkParser(site)
    parser.feed(html)
    problems = Counter(p for item in parser.links for p in item["problems"])
    hosts = Counter(item["host"] for item in parser.links)
    review_hosts = sorted({item["host"] for item in parser.links
                           if item["externalHostNeedsReview"]})
    count = len(parser.links)
    return {
        "site": site, "inspection": "LIVE_STATIC_HTML",
        "ctaCount": count,
        "status": ("NO_RENDERED_CTA" if count == 0
                   else "UNSAFE_LINK_CONTRACT" if problems
                   else "PASS_WITH_HOST_REVIEW" if review_hosts else "PASS"),
        "problemCounts": dict(sorted(problems.items())),
        "destinationHostCounts": dict(sorted(hosts.items())),
        "hostsNeedingReview": review_hosts,
        "interpretation": ("Zero rendered CTAs may reflect no eligible products; "
                           "it is not proof of market unavailability or broken publication."),
    }


def audit_camp_source(source):
    """CAMP JS is not a DOM. Report source markers as distinct evidence."""
    checks = {
        "productCard": "data-affiliate=" in source and "楽天で価格・在庫を確認" in source,
        "shoppingList": "これを楽天で買う" in source and "data-affiliate=" in source,
        "linkProtection": 'rel="sponsored nofollow noopener"' in source,
        "sourceAttribution": "affiliateClickSource(route)" in source,
    }
    return {"site": "sotojitaku", "inspection": "LIVE_JS_SOURCE_ONLY",
            "sourceContract": checks, "status": (
                "SOURCE_CONTRACT_PRESENT" if all(checks.values()) else "SOURCE_CONTRACT_MISSING"),
            "interpretation": ("Cannot prove rendered eligible checkout links "
                               "without browser interaction; never infer stock or sales.")}


def fetch_public(path):
    request = Request(ORIGIN + path, headers={
        "User-Agent": "STU-Affiliate-Contract-ReadOnly/1.0",
        "Accept": "text/html,application/javascript,*/*;q=0.7",
    })
    with urlopen(request, timeout=15) as response:
        data = response.read(3_000_000).decode("utf-8", "replace")
        return response.status, response.geturl(), data


def main():
    results = []
    for site, path in TARGETS:
        try:
            status, final_url, body = fetch_public(path)
            if status != 200 or final_url.rstrip("/") != (ORIGIN + path).rstrip("/"):
                result = {"site": site, "status": "HTTP_OR_REDIRECT_MISMATCH",
                          "httpStatus": status}
            else:
                result = audit_html(site, body)
        except (HTTPError, URLError, TimeoutError, OSError) as error:
            result = {"site": site, "status": "FETCH_FAILED",
                      "errorType": type(error).__name__}
        results.append(result)
        print(site, result["status"], result.get("ctaCount", "n/a"))
    try:
        status, final_url, body = fetch_public(CAMP_PATH)
        if status != 200 or final_url != ORIGIN + CAMP_PATH:
            result = {"site": "sotojitaku", "status": "HTTP_OR_REDIRECT_MISMATCH",
                      "httpStatus": status}
        else:
            result = audit_camp_source(body)
    except (HTTPError, URLError, TimeoutError, OSError) as error:
        result = {"site": "sotojitaku", "status": "FETCH_FAILED",
                  "errorType": type(error).__name__}
    results.append(result)
    print("sotojitaku", result["status"])
    failures = [r for r in results if r["status"] in (
        "UNSAFE_LINK_CONTRACT", "SOURCE_CONTRACT_MISSING", "FETCH_FAILED",
        "HTTP_OR_REDIRECT_MISMATCH")]
    report = {"schemaVersion": 1, "observedAt": datetime.now(timezone.utc).isoformat(),
              "scope": "five static HTML CTAs plus CAMP client source; no affiliate requests",
              "sites": results, "failures": len(failures)}
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    print("SUMMARY", json.dumps({
        "sites": len(results), "failures": len(failures),
        "renderedCtas": sum(r.get("ctaCount", 0) for r in results),
    }, ensure_ascii=False))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
