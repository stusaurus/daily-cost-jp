"""Generate a daily Open Graph image for /today/ and inject social meta tags.

The script is intentionally isolated from the core site builder so an OG-image
problem never needs to block the daily deals data build. It reads the already
created site/today/data.json, renders a 1200x630 PNG, and adds cache-busted
Open Graph / X card tags to site/today/index.html.
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

SITE = "https://stusaurus.github.io/daily-cost-jp/"
TODAY_DIR = Path("site/today")
DATA = TODAY_DIR / "data.json"
HTML = TODAY_DIR / "index.html"
OG = TODAY_DIR / "og.png"
JST = ZoneInfo("Asia/Tokyo")

WIDTH = 1200
HEIGHT = 630
BG = "#FBF7F3"
CARD = "#FFFFFF"
TEXT = "#252525"
MUTED = "#746A64"
ACCENT = "#B3261E"
LINE = "#E8DDD6"


def fnum(value, default=0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def money(value: float) -> str:
    if value >= 100:
        return f"¥{value:,.0f}"
    if value >= 10:
        return f"¥{value:,.1f}"
    return f"¥{value:,.2f}"


def find_font(prefer_bold: bool = False) -> tuple[str | None, bool]:
    """Return (font_path, supports_japanese_expected)."""
    preferred = [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc" if prefer_bold else "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJKjp-Bold.otf" if prefer_bold else "/usr/share/fonts/opentype/noto/NotoSansCJKjp-Regular.otf",
        "/usr/share/fonts/truetype/noto/NotoSansJP-Bold.ttf" if prefer_bold else "/usr/share/fonts/truetype/noto/NotoSansJP-Regular.ttf",
        "/usr/share/fonts/opentype/ipafont-gothic/ipagp.ttf",
        "/usr/share/fonts/truetype/fonts-japanese-gothic.ttf",
    ]
    for candidate in preferred:
        if Path(candidate).exists():
            return candidate, True

    roots = [Path("/usr/share/fonts"), Path("/usr/local/share/fonts")]
    wanted = ("notosanscjk", "notosansjp", "ipag", "ipaexg")
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.suffix.lower() not in {".ttf", ".otf", ".ttc"}:
                continue
            compact = path.name.lower().replace("-", "").replace("_", "")
            if any(token in compact for token in wanted):
                if prefer_bold and "bold" not in compact:
                    continue
                return str(path), True

    fallback = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if prefer_bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    if Path(fallback).exists():
        return fallback, False
    return None, False


def load_font(ImageFont, size: int, bold: bool = False):
    path, supports_japanese = find_font(bold)
    if path:
        try:
            return ImageFont.truetype(path, size=size), supports_japanese
        except Exception:
            pass
    return ImageFont.load_default(), False


def rounded_rectangle(draw, box, radius, fill, outline=None, width=1):
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def render_png(payload: dict) -> None:
    from PIL import Image, ImageDraw, ImageFont

    image = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(image)

    title_font, jp = load_font(ImageFont, 66, bold=True)
    brand_font, _ = load_font(ImageFont, 28, bold=True)
    date_font, _ = load_font(ImageFont, 25, bold=False)
    item_font, _ = load_font(ImageFont, 31, bold=True)
    value_font, _ = load_font(ImageFont, 31, bold=True)
    unit_font, _ = load_font(ImageFont, 22, bold=False)
    footer_font, _ = load_font(ImageFont, 22, bold=False)

    generated = payload.get("generated_at")
    try:
        now = datetime.fromisoformat(str(generated)).astimezone(JST) if generated else datetime.now(JST)
    except Exception:
        now = datetime.now(JST)

    if jp:
        brand = "日用品コスパ比較"
        title = "今日の買い候補5選"
        date_text = f"{now.year}年{now.month}月{now.day}日 更新"
        footer = "楽天送料込み・単価換算で毎朝比較"
        fallback_message = "本日の比較データを更新しました"
    else:
        # Keep the fallback legible even on runners without a Japanese font.
        brand = "DAILY COST JP"
        title = "Today's Daily Deals"
        date_text = now.strftime("%Y-%m-%d updated")
        footer = "Shipping-included unit-price comparison"
        fallback_message = "Daily comparison data updated"

    # Header accent and brand.
    draw.rectangle((0, 0, WIDTH, 14), fill=ACCENT)
    draw.text((72, 54), brand, font=brand_font, fill=ACCENT)
    draw.text((72, 100), title, font=title_font, fill=TEXT)
    draw.text((74, 184), date_text, font=date_font, fill=MUTED)

    items = list(payload.get("items") or [])[:3]
    y = 238
    row_h = 92
    gap = 13

    if items:
        for index, row in enumerate(items, start=1):
            top = y + (index - 1) * (row_h + gap)
            rounded_rectangle(draw, (70, top, 1130, top + row_h), 18, CARD, LINE, 2)

            # Rank marker.
            draw.ellipse((91, top + 22, 139, top + 70), fill=TEXT)
            rank_font, _ = load_font(ImageFont, 23, bold=True)
            rank_text = str(index)
            bbox = draw.textbbox((0, 0), rank_text, font=rank_font)
            tx = 115 - (bbox[2] - bbox[0]) / 2
            ty = top + 46 - (bbox[3] - bbox[1]) / 2 - 2
            draw.text((tx, ty), rank_text, font=rank_font, fill="#FFFFFF")

            name = str(row.get("name") or row.get("id") or "")
            if not jp:
                name = str(row.get("id") or "Daily item").replace("-", " ").title()
            if len(name) > 20:
                name = name[:19] + "…"

            discount = fnum(row.get("discount"))
            unit_price = fnum(row.get("unit_price"))
            metric_label = str(row.get("metric_label") or row.get("metric") or "")
            if not jp and metric_label:
                metric_label = str(row.get("metric") or metric_label)

            draw.text((162, top + 25), name, font=item_font, fill=TEXT)
            discount_text = f"約{discount:.0f}%安い" if jp else f"~{discount:.0f}% lower"
            draw.text((570, top + 25), discount_text, font=value_font, fill=ACCENT)
            price_text = f"{money(unit_price)} / {metric_label}" if metric_label else money(unit_price)
            draw.text((842, top + 31), price_text, font=unit_font, fill=TEXT)
    else:
        rounded_rectangle(draw, (70, 255, 1130, 410), 22, CARD, LINE, 2)
        draw.text((110, 308), fallback_message, font=item_font, fill=TEXT)

    draw.text((72, 585), footer, font=footer_font, fill=MUTED)
    image.save(OG, format="PNG", optimize=True)


def inject_meta(payload: dict) -> None:
    if not HTML.exists():
        return
    markup = HTML.read_text(encoding="utf-8")

    # Remove our tags before reinserting so repeated builds never duplicate them.
    patterns = [
        r'\s*<meta property="og:type"[^>]*>',
        r'\s*<meta property="og:image"[^>]*>',
        r'\s*<meta property="og:image:width"[^>]*>',
        r'\s*<meta property="og:image:height"[^>]*>',
        r'\s*<meta name="twitter:card"[^>]*>',
        r'\s*<meta name="twitter:image"[^>]*>',
        r'\s*<meta name="twitter:title"[^>]*>',
        r'\s*<meta name="twitter:description"[^>]*>',
    ]
    for pattern in patterns:
        markup = re.sub(pattern, "", markup, flags=re.IGNORECASE)

    try:
        date = datetime.fromisoformat(str(payload.get("generated_at"))).astimezone(JST)
    except Exception:
        date = datetime.now(JST)
    version = date.strftime("%Y%m%d")
    image_url = f"{SITE}today/og.png?v={version}"
    title = f"今日の買い候補5選｜{date.year}年{date.month}月{date.day}日"
    description = "楽天市場の日用品を送料込み・単価換算で毎朝自動比較。今日の買い候補をデータから紹介します。"

    tags = (
        '\n<meta property="og:type" content="website">'
        f'\n<meta property="og:image" content="{image_url}">'
        f'\n<meta property="og:image:width" content="{WIDTH}">'
        f'\n<meta property="og:image:height" content="{HEIGHT}">'
        '\n<meta name="twitter:card" content="summary_large_image">'
        f'\n<meta name="twitter:image" content="{image_url}">'
        f'\n<meta name="twitter:title" content="{title}">'
        f'\n<meta name="twitter:description" content="{description}">'
    )

    og_url = re.search(r'<meta property="og:url"[^>]*>', markup, flags=re.IGNORECASE)
    if og_url:
        insert_at = og_url.end()
        markup = markup[:insert_at] + tags + markup[insert_at:]
    else:
        markup = markup.replace("</head>", tags + "\n</head>", 1)
    HTML.write_text(markup, encoding="utf-8")


def main() -> None:
    TODAY_DIR.mkdir(parents=True, exist_ok=True)
    if DATA.exists():
        try:
            payload = json.loads(DATA.read_text(encoding="utf-8"))
        except Exception:
            payload = {}
    else:
        payload = {}

    if not payload:
        now = datetime.now(JST)
        payload = {
            "date": now.date().isoformat(),
            "generated_at": now.isoformat(),
            "items": [],
        }

    try:
        render_png(payload)
        print(f"Generated daily OG image: {OG} ({WIDTH}x{HEIGHT})")
    except Exception as exc:
        # The workflow step is also non-blocking, but keep the failure explicit.
        print(f"WARNING: Could not generate daily OG image: {exc}")
        return

    try:
        inject_meta(payload)
        print("Injected Open Graph and X card metadata into /today/")
    except Exception as exc:
        print(f"WARNING: Could not inject daily OG metadata: {exc}")


if __name__ == "__main__":
    main()
