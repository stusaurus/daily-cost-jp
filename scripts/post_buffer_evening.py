"""Publish a second, different evening X post from today's trusted deal set."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import post_buffer as buffer
from x_post_strategy import choose_variant, strategy_version

JST = ZoneInfo("Asia/Tokyo")


def evening_url(payload: dict, variant: int, category_id: str) -> str:
    payload_date = str(payload.get("date") or "").strip()
    try:
        date_tag = datetime.fromisoformat(payload_date).strftime("%Y%m%d")
    except ValueError:
        date_tag = datetime.now(JST).strftime("%Y%m%d")
    safe_category = "".join(ch for ch in category_id.lower() if ch.isalnum() or ch in {"-", "_"})[:30] or "daily"
    content = f"evening_v{variant}_s{strategy_version()}_{safe_category}_{date_tag}"
    return (
        buffer.PLAIN_TODAY_URL
        + "?utm_source=x&utm_medium=social&utm_campaign=daily_deals"
        + f"&utm_content={content}"
    )


def money(value: object) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = 0.0
    if number >= 100:
        return f"¥{number:,.0f}"
    if number >= 10:
        return f"¥{number:,.1f}"
    return f"¥{number:,.2f}"


def build_evening_text(payload: dict) -> str:
    items = list(payload.get("items") or [])
    if not items:
        buffer.fail("Today's social payload has no deal items for evening post")

    # Morning copy normally highlights the first three items. Rotate through
    # the remaining candidates so the evening spotlight does not keep picking
    # the same fourth-ranked category on consecutive days.
    candidates = items[3:] if len(items) >= 4 else items
    payload_date = str(payload.get("date") or "").strip()
    try:
        day_seed = datetime.fromisoformat(payload_date).date().toordinal()
    except ValueError:
        day_seed = datetime.now(JST).date().toordinal()
    item = candidates[day_seed % len(candidates)]

    name = str(item.get("name") or "日用品")
    product = str(item.get("product_name") or "").strip()
    if len(product) > 44:
        product = product[:43] + "…"
    try:
        discount = float(item.get("discount") or 0)
    except (TypeError, ValueError):
        discount = 0.0
    metric = str(item.get("metric_label") or item.get("metric") or "")
    unit = money(item.get("unit_price"))

    variant = choose_variant("evening", payload_date or str(day_seed), 5)
    headers = [
        f"【今夜の買い候補｜{name}】",
        f"【今日の1品チェック｜{name}】",
        f"【買う前に単価チェック｜{name}】",
        f"【今夜の価格メモ｜{name}】",
        f"【今日の比較で気になった1品｜{name}】",
    ]
    lead_lines = [
        f"比較候補の中央値より約{discount:.0f}%安い候補を確認。",
        f"今日の比較では、中央値より約{discount:.0f}%低い候補。",
        f"送料込み単価で見ると、比較中央値より約{discount:.0f}%安め。",
        f"同じ単位で比べると、中央値より約{discount:.0f}%差がありました。",
        f"今日取得した候補内で、中央値より約{discount:.0f}%安い水準。",
    ]
    ctas = [
        "店頭価格と比べる前の目安に👇",
        "買う前の価格チェックはこちら👇",
        "今日の買い候補と比較根拠を見る👇",
        "店頭と楽天、どちらが得か見る前に👇",
        "ほかの買い候補もまとめて確認👇",
    ]

    lines = [headers[variant], lead_lines[variant]]
    if product:
        lines.append(product)
    if metric:
        lines.append(f"送料込み単価 {unit} / {metric}")
    lines.extend([
        ctas[variant],
        evening_url(payload, variant, str(item.get("id") or "")),
        "※当日取得できた比較候補内の目安",
        "※楽天アフィリエイトを利用しています",
    ])
    text = "\n".join(lines)
    if len(text) > 280:
        # Product name is the least important optional line.
        lines = [line for line in lines if line != product]
        text = "\n".join(lines)
    if len(text) > 280:
        buffer.fail(f"Generated evening X post is {len(text)} characters; expected <= 280")
    return text


def main() -> None:
    payload = buffer.fetch_today_social()
    text = build_evening_text(payload)
    org_id, org_name, channel = buffer.discover_x_channel()
    channel_id = str(channel.get("id") or "")
    print(
        f"Target evening Buffer channel: organization={org_name or org_id}, "
        f"service={channel.get('service')}, name={channel.get('name')}"
    )
    if buffer.was_already_posted(org_id, channel_id, text):
        return
    buffer.publish_now(channel_id, text)


if __name__ == "__main__":
    main()
