"""Read-only live release evidence for the six comparison websites.

No prices, SKU identifiers, affiliate targets, user information or secrets are
collected. A missing conditional purchase UI is never called a deployment defect
unless its real inventory gate is independently proven eligible.
"""
import argparse
import json
import time
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ORIGIN = "https://stusaurus.github.io"
REPORT = Path("audit-results/six-site-live-release.json")

CHECKS = [
    {"site": "daily", "path": "/daily-cost-jp/categories/laundry/",
     "kind": "html", "marker": 'id="store-comparison-title"', "required": True},
    {"site": "baby", "path": "/baby-cost-jp/diapers/",
     "kind": "html", "marker": 'data-nav-source="diaper_index_planner"',
     "required": False},
    {"site": "baby", "path": "/baby-cost-jp/diapers/pants/m/",
     "kind": "html", "marker": 'id="purchase-planner"',
     "required": False, "allow_noindex": True},
    {"site": "baby", "path": "/baby-cost-jp/diapers/pants/m/",
     "kind": "html", "marker": 'data-purchase-size-choice="7"',
     "required": True, "allow_noindex": True},
    {"site": "food", "path": "/food-cost-jp/categories/pack-rice/",
     "kind": "html", "marker": "必要な食数から購入箱数",
     "required": False, "allow_noindex": True},
    {"site": "food", "path": "/food-cost-jp/assets/pack-rice-planner.js",
     "kind": "javascript", "marker": "calculateWithStock", "required": True},
    {"site": "food", "path": "/food-cost-jp/assets/pack-rice-planner.js",
     "kind": "javascript", "marker": "data-rice-meal-choice", "required": True},
    {"site": "food", "path": "/food-cost-jp/guides/pack-rice-24-servings-cost/",
     "kind": "html", "marker": 'data-rice-meal-choice="2"',
     "required": False, "allow_noindex": True},
    {"site": "food", "path": "/food-cost-jp/guides/pack-rice-24-servings-cost/",
     "kind": "html", "marker": 'data-rice-quantity-only',
     "alternateMarkers": ['data-rice-planner'],
     "required": True, "allow_noindex": True},
    {"site": "food", "path": "/food-cost-jp/assets/pack-rice-quantity-only.js",
     "kind": "javascript", "marker": 'function countOnly(daily,days,stock)',
     "required": True},
    {"site": "kyo-bodo", "path": "/kyo-bodo-jp/scenes/two-player/",
     "kind": "html", "marker": "2人専用／複数人数対応", "required": True},
    {"site": "kyo-bodo", "path": "/kyo-bodo-jp/scenes/two-player/",
     "kind": "html", "marker": "data-two-player-quick-filter", "required": True},
    {"site": "kyo-bodo", "path": "/kyo-bodo-jp/assets/two-player-quick-filter.js",
     "kind": "javascript", "marker": "data-two-quick-count", "required": True},
    {"site": "pet", "path": "/pet-cost-jp/",
     "kind": "html", "marker": "data-monthly-sheet-entry", "required": True},
    {"site": "pet", "path": "/pet-cost-jp/categories/pet-sheets/",
     "kind": "html", "marker": 'id="monthly-sheet-guide-heading"',
     "required": True},
    {"site": "pet", "path": "/pet-cost-jp/categories/pet-sheets/",
     "kind": "html", "marker": 'data-usage-preset="3"', "required": True},
    {"site": "sotojitaku", "path": "/sotojitaku/camp/",
     "kind": "html", "marker": 'type="module"', "required": True},
    {"site": "sotojitaku", "path": "/sotojitaku/camp/app.js",
     "kind": "javascript", "marker": "createCAMPVisitGate", "required": True},
    {"site": "sotojitaku", "path": "/sotojitaku/camp/funnel-metrics.js",
     "kind": "javascript", "marker": "createCAMPVisitGate", "required": True},
]


class Headings(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.canonical = None
        self.noindex = False
        self.h1 = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "link" and "canonical" in attrs.get("rel", "").lower().split():
            self.canonical = attrs.get("href")
        if tag == "meta" and attrs.get("name", "").lower() == "robots":
            self.noindex = "noindex" in attrs.get("content", "").lower()
        if tag == "h1":
            self.h1 += 1


def assess(spec, body, status_code=200, final_url=None):
    """Evaluate only verified HTML/JS evidence, never current product claims."""
    expected = ORIGIN + spec["path"]
    # A verified food offer swaps the count-only fallback for a priced planner.
    # Either is valid evidence of a usable page. Never require both simultaneously.
    accepted = [spec["marker"], *spec.get("alternateMarkers", [])]
    matched = next((marker for marker in accepted if marker in body), None)
    result = {"site": spec["site"], "url": expected,
              "httpStatus": status_code, "marker": spec["marker"],
              "requiredMarker": spec["required"],
              "markerPresent": matched is not None,
              "matchedMarker": matched}
    if status_code != 200:
        result["status"] = "HTTP_ERROR"
        return result
    if final_url is not None and final_url.rstrip("/") != expected.rstrip("/"):
        result["status"] = "REDIRECTED"
        result["redirectedTo"] = final_url
        return result
    if spec["kind"] == "html":
        parser = Headings()
        parser.feed(body)
        result["canonical"] = parser.canonical
        result["h1Count"] = parser.h1
        result["noindex"] = parser.noindex
        if (parser.canonical != expected or parser.h1 < 1 or
                (parser.noindex and not spec.get("allow_noindex"))):
            result["status"] = "SEO_METADATA_MISMATCH"
            return result
    if not result["markerPresent"]:
        result["status"] = ("FEATURE_MISSING" if spec["required"]
                            else "CONDITIONAL_FEATURE_NOT_SHOWN")
        return result
    result["status"] = "PASS"
    return result


def fetch(spec):
    """Fetch public HTML/JS with one bounded retry for transient server errors."""
    url = ORIGIN + spec["path"]
    for attempt in range(2):
        request = Request(url, headers={
            "User-Agent": "STU-SixSite-ReadOnly-Release-Check/1.0",
            "Accept": "text/html,application/javascript,*/*;q=0.7",
        })
        try:
            with urlopen(request, timeout=15) as response:
                payload = response.read(3_000_000)
                body = payload.decode("utf-8", errors="replace")
                return assess(spec, body, response.status, response.geturl())
        except HTTPError as exc:
            if attempt == 0 and exc.code in (429, 500, 502, 503, 504):
                time.sleep(1)
                continue
            return assess(spec, "", exc.code)
        except (URLError, TimeoutError, OSError) as exc:
            if attempt == 0:
                time.sleep(1)
                continue
            return {"site": spec["site"], "url": url, "status": "NETWORK_ERROR",
                    "errorType": type(exc).__name__}
    raise AssertionError("bounded fetch loop must return")


def make_report(results, observed_at=None):
    timestamp = observed_at or datetime.now(timezone.utc).isoformat()
    failed = [result for result in results
              if result["status"] not in ("PASS", "CONDITIONAL_FEATURE_NOT_SHOWN")]
    return {
        "schemaVersion": 1,
        "observedAt": timestamp,
        "scope": "publicly served HTML and JavaScript, not search index or sales",
        "checked": len(results),
        "passed": sum(result["status"] == "PASS" for result in results),
        "conditionalNotShown": sum(
            result["status"] == "CONDITIONAL_FEATURE_NOT_SHOWN" for result in results),
        "failures": len(failed),
        "checks": results,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, default=REPORT)
    args = parser.parse_args()
    results = []
    for spec in CHECKS:
        outcome = fetch(spec)
        print(f"{outcome['site']}: {spec['path']} => {outcome['status']}")
        results.append(outcome)
    report = make_report(results)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n",
                           encoding="utf-8")
    print("RESULT:", json.dumps({key: report[key] for key in
          ("checked", "passed", "conditionalNotShown", "failures")}, ensure_ascii=False))
    return 1 if report["failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
