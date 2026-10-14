#!/usr/bin/env python3
"""Read-only, six-property Search Console report. Never treats failures as zero."""
import datetime as dt
import json
import math
import os
from pathlib import Path
from urllib.parse import quote, urlsplit
from zoneinfo import ZoneInfo

ROOT = "https://www.googleapis.com/webmasters/v3"
SCOPE = "https://www.googleapis.com/auth/webmasters.readonly"
SITES = (
    ("日用品", "https://stusaurus.github.io/daily-cost-jp/"),
    ("ベビー用品", "https://stusaurus.github.io/baby-cost-jp/"),
    ("ペット用品", "https://stusaurus.github.io/pet-cost-jp/"),
    ("食品", "https://stusaurus.github.io/food-cost-jp/"),
    ("ボードゲーム", "https://stusaurus.github.io/kyo-bodo-jp/"),
    ("SOTOJITAKU", "https://stusaurus.github.io/sotojitaku/"),
)
OUTPUT = Path("audit-results")
AUTHORIZED_LEVELS = {"siteOwner", "siteFullUser", "siteRestrictedUser"}


class InvalidMetrics(ValueError):
    """Only approved finite aggregate numbers may enter diagnostics."""
    def __init__(self, values):
        super().__init__("invalid metrics values")
        self.metrics = dict(zip(("clicks", "impressions", "ctr", "position"), values))


def date_windows(today):
    """Exclude the most recent three Pacific calendar days for GSC final data."""
    end = today - dt.timedelta(days=3)

    def window(n, lag=0):
        last = end - dt.timedelta(days=lag)
        return [str(last - dt.timedelta(days=n - 1)), str(last)]

    return {
        "last_7": window(7),
        "prior_7": window(7, 7),
        "last_28": window(28),
        "prior_28": window(28, 28),
    }


def safe_metrics(row):
    if not isinstance(row, dict):
        raise ValueError("invalid metrics row")
    values = [row.get(k) for k in ("clicks", "impressions", "ctr", "position")]
    if any(type(x) not in (int, float) or not math.isfinite(x) for x in values):
        raise ValueError("missing metrics")
    clicks, impressions, ctr, position = values
    if (clicks < 0 or impressions < 0 or int(clicks) != clicks
            or int(impressions) != impressions or not 0 <= ctr <= 1
            or position < 1 or clicks > impressions):
        raise InvalidMetrics(values)
    return {
        "clicks": int(clicks),
        "impressions": int(impressions),
        "ctr": round(float(ctr), 6),
        "position": round(float(position), 2),
    }


def aggregate(payload):
    if not isinstance(payload, dict):
        raise ValueError("invalid response")
    rows = payload.get("rows", [])
    if not isinstance(rows, list):
        raise ValueError("invalid rows")
    if not rows:
        return {"status": "NO_ROWS", "metrics": None}
    if len(rows) != 1 or rows[0].get("keys"):
        raise ValueError("unexpected aggregate dimensions")
    return {"status": "OBSERVED", "metrics": safe_metrics(rows[0])}


def safe_page(url, site):
    """Reject other github.io projects; paths must remain under this exact prefix."""
    try:
        p, base = urlsplit(url), urlsplit(site)
        if (p.scheme != "https" or p.netloc != base.netloc or
                p.username or p.password or not p.path.startswith(base.path)):
            return None
        path = "/" + p.path[len(base.path):]
        if any(ch in path for ch in ("\n", "\r", "\x00", "|")):
            return None
        return path
    except (ValueError, TypeError):
        return None


def page_summary(payload, site, limit=5):
    if not isinstance(payload, dict) or not isinstance(payload.get("rows", []), list):
        raise ValueError("invalid page response")
    rows = payload.get("rows", [])
    pages = []
    for row in rows:
        keys = row.get("keys")
        if not isinstance(keys, list) or len(keys) != 1:
            raise ValueError("invalid page key")
        path = safe_page(keys[0], site)
        if path is not None:
            pages.append({"path": path, **safe_metrics(row)})
    pages.sort(key=lambda r: (-r["impressions"], -r["clicks"], r["path"]))
    return {
        "status": "TOP_ROW_LIMIT_POSSIBLE" if len(rows) >= 1000 else "OBSERVED_TOP_ROWS",
        "rows_returned": len(rows),
        "top_pages": pages[:limit],
    }


def change(current, prior):
    if current is None or prior is None:
        return {"status": "UNKNOWN", "change_impressions": None}
    delta = current["impressions"] - prior["impressions"]
    before = prior["impressions"]
    if before >= 20 and current["impressions"] <= before * 0.5:
        status = "OBSERVED_DECLINE"
    elif current["impressions"] >= 20 and current["impressions"] >= 1.5 * max(1, before):
        status = "OBSERVED_INCREASE"
    elif before + current["impressions"] < 20:
        status = "LOW_SAMPLE"
    else:
        status = "OBSERVE"
    return {
        "status": status,
        "change_impressions": delta,
        "change_percent": round(delta * 100 / before, 1) if before else None,
    }


def query(session, site, window, dimensions=None):
    body = {
        "startDate": window[0], "endDate": window[1],
        "type": "web", "dataState": "final",
    }
    if dimensions:
        body.update({"dimensions": dimensions, "rowLimit": 1000})
    endpoint = ROOT + "/sites/" + quote(site, safe="") + "/searchAnalytics/query"
    response = session.post(endpoint, json=body, timeout=45)
    if response.status_code != 200:
        raise RuntimeError("SEARCH_ANALYTICS_HTTP_" + str(response.status_code))
    return response.json()


def analyze_site(session, name, site, windows, permissions):
    result = {
        "name": name, "property": site, "status": "NOT_CONNECTED",
        "windows": {}, "top_pages": [], "changes": {},
    }
    if permissions is None:
        result["reason"] = "PROPERTY_LIST_UNAVAILABLE"
        return result
    if permissions.get(site) not in AUTHORIZED_LEVELS:
        result["reason"] = "PROPERTY_ACCESS_MISSING"
        return result
    stage = "aggregate"
    try:
        aggregates = {}
        for key, value in windows.items():
            stage = key
            aggregates[key] = aggregate(query(session, site, value))
        stage = "top_pages"
        pages = page_summary(query(session, site, windows["last_28"], ["page"]), site)
        result.update({
            "status": "OBSERVED" if any(x["status"] == "OBSERVED" for x in aggregates.values())
                      else "NO_ROWS",
            "windows": aggregates,
            "page_coverage": {k: pages[k] for k in ("status", "rows_returned")},
            "top_pages": pages["top_pages"],
            "changes": {
                "week": change(aggregates["last_7"]["metrics"], aggregates["prior_7"]["metrics"]),
                "month": change(aggregates["last_28"]["metrics"], aggregates["prior_28"]["metrics"]),
            },
        })
    except InvalidMetrics as error:
        result["reason"] = "INVALID_API_RESPONSE"
        result["diagnostic"] = {"stage": stage, "metrics": error.metrics}
    except (ValueError, KeyError, TypeError):
        result["reason"] = "INVALID_API_RESPONSE"
        result["diagnostic"] = {"stage": stage}
    except Exception:
        result["reason"] = "SEARCH_CONSOLE_API_UNAVAILABLE"
    return result


def make_report(today, session=None, permissions=None, auth_problem=None):
    windows = date_windows(today)
    entries = []
    for name, site in SITES:
        if auth_problem:
            entries.append({
                "name": name, "property": site, "status": "NOT_CONNECTED",
                "reason": auth_problem, "windows": {}, "top_pages": [], "changes": {},
            })
        else:
            entries.append(analyze_site(session, name, site, windows, permissions))
    observed = sum(1 for x in entries if x["status"] in ("OBSERVED", "NO_ROWS"))
    return {
        "source": "Google Search Console Search Analytics API (read-only)",
        "data_timezone": "America/Los_Angeles",
        "as_of": str(today),
        "date_windows": windows,
        "status": "READY" if observed == len(SITES) else "PARTIAL" if observed else "UNAVAILABLE",
        "sites": entries,
        "notes": [
            "NOT_CONNECTED is not zero impressions; a no-row response is not proof of zero traffic.",
            "Search Console clicks are not X referral visits, GA4 sessions, or Rakuten conversions.",
            "Search Analytics may omit anonymized queries and some low-volume/page rows.",
            "No published-site changes, index submissions, credential files, or automatic SEO rewrites.",
        ],
    }


def markdown(report):
    lines = [
        "# 6サイト Google検索流入レポート",
        "",
        "- 集計状態：**" + report["status"] + "**",
        "- 集計基準日（太平洋時間）：" + report["as_of"],
        "- 直近28日：" + "〜".join(report["date_windows"]["last_28"]),
        "- 直近7日：" + "〜".join(report["date_windows"]["last_7"]),
        "",
        "| サイト | 28日表示 | 28日クリック | CTR | 平均順位 | 前週比（表示） | 状態 |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for item in report["sites"]:
        metrics = item["windows"].get("last_28", {}).get("metrics") or {}
        weekly = item["changes"].get("week", {})
        def number(key, digits=None):
            v = metrics.get(key)
            if v is None:
                return "不明"
            return (str(round(v * 100, 2)) + "%" if key == "ctr"
                    else str(v))
        delta = weekly.get("change_impressions")
        lines.append("| " + item["name"] + " | " +
                     " | ".join([number("impressions"), number("clicks"), number("ctr"),
                                 number("position"), str(delta) if delta is not None else "不明",
                                 item["status"] if "reason" not in item else item["reason"]]) +
                     " |")
    lines.extend(["", "## 7日・28日の前期間比較", "",
                  "| サイト | 期間 | 現在表示 / クリック | 前期間表示 / クリック | 表示増減 | クリック増減 | 判定 |",
                  "|---|---|---:|---:|---:|---:|---|"])
    for item in report["sites"]:
        for label, current_key, prior_key, change_key in (
                ("7日", "last_7", "prior_7", "week"),
                ("28日", "last_28", "prior_28", "month")):
            current = item["windows"].get(current_key, {}).get("metrics")
            prior = item["windows"].get(prior_key, {}).get("metrics")
            signal = item["changes"].get(change_key, {})
            def pair(metrics):
                return (str(metrics["impressions"]) + " / " + str(metrics["clicks"])) if metrics else "不明"
            delta = signal.get("change_impressions")
            percentage = signal.get("change_percent")
            delta_text = str(delta) if delta is not None else "不明"
            if percentage is not None:
                delta_text += " (" + str(percentage) + "%)"
            clicks = str(current["clicks"] - prior["clicks"]) if current and prior else "不明"
            lines.append("| " + " | ".join([item["name"], label, pair(current), pair(prior),
                                            delta_text, clicks, signal.get("status", "UNKNOWN")]) + " |")
    lines.extend(["", "前7日：" + "〜".join(report["date_windows"]["prior_7"]),
                  "前28日：" + "〜".join(report["date_windows"]["prior_28"]), ""])
    lines.extend(["", "## 主な検索表示ページ（直近28日・最大5件/サイト）", ""])
    for item in report["sites"]:
        lines.append("### " + item["name"])
        if not item["top_pages"]:
            lines.append("ページ別データは未取得／非表示。0回とは断定しません。")
        else:
            for page in item["top_pages"]:
                lines.append("- " + page["path"] + "：表示 " +
                             str(page["impressions"]) + "、クリック " + str(page["clicks"]))
        lines.append("")
    lines.extend(["※検索表示の増減だけでは順位低下・ペナルティ・インデックス問題と断定できません。",
                  "※Xのアクセス解析と楽天の売上実績は別集計です。",
                  "※Search Consoleへの書込み、サイトの変更、商品・価格・楽天リンクの更新はしていません。", ""])
    return "\n".join(lines)


def write_report(report):
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "gsc-six-sites.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    (OUTPUT / "gsc-six-sites.md").write_text(markdown(report), encoding="utf-8")


def main():
    today = dt.datetime.now(ZoneInfo("America/Los_Angeles")).date()
    if not os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
        report = make_report(today, auth_problem="GOOGLE_CREDENTIALS_MISSING")
    else:
        try:
            import google.auth
            from google.auth.transport.requests import AuthorizedSession
            credentials, _ = google.auth.default(scopes=[SCOPE])
            session = AuthorizedSession(credentials)
            response = session.get(ROOT + "/sites", timeout=30)
            if response.status_code != 200:
                report = make_report(today, auth_problem="PROPERTY_LIST_HTTP_" + str(response.status_code))
            else:
                obj = response.json()
                if not isinstance(obj, dict) or not isinstance(obj.get("siteEntry", []), list):
                    raise ValueError("bad property list")
                permissions = {
                    row["siteUrl"]: row["permissionLevel"]
                    for row in obj.get("siteEntry", [])
                    if isinstance(row, dict) and isinstance(row.get("siteUrl"), str)
                    and isinstance(row.get("permissionLevel"), str)
                }
                report = make_report(today, session=session, permissions=permissions)
        except Exception:
            report = make_report(today, auth_problem="AUTH_OR_PROPERTY_LIST_FAILED")
    write_report(report)
    print("Six-site GSC read-only status: " + report["status"])
    if report["status"] != "READY":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
