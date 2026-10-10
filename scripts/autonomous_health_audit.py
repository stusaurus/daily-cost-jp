#!/usr/bin/env python3
"""Read-only production availability audit; never modifies the site."""
import json
import os
import sys
import time
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BASE = "https://stusaurus.github.io/daily-cost-jp"
PATHS = ["/", "/categories/laundry/", "/categories/tissue/", "/categories/toilet-paper/", "/sitemap.xml"]

def check(path):
    url = BASE + path
    last_error = None
    for attempt in range(3):
        try:
            with urlopen(Request(url, headers={"User-Agent": "DailyCost-HealthAudit/1.0"}), timeout=15) as response:
                status = response.status
                body = response.read(150000)
                if status != 200 or not body:
                    raise ValueError(f"HTTP {status} or empty response")
                return {"path": path, "status": "pass", "http_status": status, "bytes_sampled": len(body)}
        except (HTTPError, URLError, TimeoutError, ValueError) as exc:
            last_error = str(exc)
            if attempt < 2:
                time.sleep(2 ** attempt)
    return {"path": path, "status": "fail", "error": last_error}

def main():
    checks = [check(path) for path in PATHS]
    report = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "audit_type": "read_only_production_health",
        "revenue": "NOT_CHECKED",
        "affiliate_clicks": "NOT_CHECKED",
        "checks": checks,
        "result": "pass" if all(c["status"] == "pass" for c in checks) else "fail",
    }
    os.makedirs("audit-results", exist_ok=True)
    with open("audit-results/health.json", "w", encoding="utf-8") as fp:
        json.dump(report, fp, ensure_ascii=False, indent=2)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    sys.exit(0 if report["result"] == "pass" else 1)

if __name__ == "__main__":
    main()
