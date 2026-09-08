"""Make missing Rakuten ranking positions explicit instead of silently skipping them."""
from __future__ import annotations

import re
from pathlib import Path

TRENDS = Path("site/trends/index.html")

STYLE = r'''
<style id="ranking-gap-style">
.rank-gap{
  grid-column:1/-1;
  padding:9px 12px;
  border:1px dashed #d9d0ca;
  border-radius:12px;
  background:#fbfaf9;
  color:#776e69;
}
.rank-gap strong{font-size:11px;color:#6b625e}
.rank-gap small{display:block;margin-top:2px;font-size:9px;line-height:1.45;color:#9a918c}
</style>
'''

CARD_RE = re.compile(r'<article class="card">.*?</article>', re.DOTALL)
RANK_RE = re.compile(r'<div class="rank"><b>(\d+)位</b>')
GRID_RE = re.compile(r'(<section class="grid">)(.*?)(</section>)', re.DOTALL)


def gap_label(start: int, end: int) -> str:
    return f"{start}位" if start == end else f"{start}〜{end}位"


def gap_block(start: int, end: int) -> str:
    label = gap_label(start, end)
    return (
        '<div class="rank-gap">'
        f'<strong>{label}：商品情報を取得できませんでした</strong>'
        '<small>楽天の公式順位は詰めずに表示しています。次回更新で再取得します。</small>'
        '</div>'
    )


def grouped_missing(missing: list[int]):
    if not missing:
        return []
    groups = []
    start = prev = missing[0]
    for rank in missing[1:]:
        if rank == prev + 1:
            prev = rank
            continue
        groups.append((start, prev))
        start = prev = rank
    groups.append((start, prev))
    return groups


def main() -> None:
    if not TRENDS.exists():
        print("Trend ranking page unavailable; skipping gap display")
        return

    markup = TRENDS.read_text(encoding="utf-8")
    match = GRID_RE.search(markup)
    if not match:
        print("Trend ranking grid not found; skipping gap display")
        return

    max_rank = 50 if "TOP50" in markup else 10
    cards = {}
    for card_match in CARD_RE.finditer(match.group(2)):
        card = card_match.group(0)
        rank_match = RANK_RE.search(card)
        if not rank_match:
            continue
        rank = int(rank_match.group(1))
        if 1 <= rank <= max_rank:
            cards[rank] = card

    if not cards:
        print("No ranking cards found; skipping gap display")
        return

    missing = [rank for rank in range(1, max_rank + 1) if rank not in cards]
    gap_by_start = {start: (start, end) for start, end in grouped_missing(missing)}
    covered = set()
    rebuilt = []

    for rank in range(1, max_rank + 1):
        if max_rank == 50 and rank == 11:
            rebuilt.append('<div class="divider" id="rank-11" style="scroll-margin-top:16px">11位〜50位</div>')

        if rank in cards:
            rebuilt.append(cards[rank])
            continue

        if rank in covered:
            continue
        group = gap_by_start.get(rank)
        if group:
            start, end = group
            rebuilt.append(gap_block(start, end))
            covered.update(range(start, end + 1))

    new_grid = match.group(1) + "".join(rebuilt) + match.group(3)
    markup = markup[:match.start()] + new_grid + markup[match.end():]

    markup = re.sub(r'<style id="ranking-gap-style">.*?</style>\s*', '', markup, flags=re.DOTALL)
    if "</head>" in markup:
        markup = markup.replace("</head>", STYLE + "\n</head>", 1)

    TRENDS.write_text(markup, encoding="utf-8")
    print(f"Made {len(missing)} missing ranking positions explicit across TOP{max_rank}")


if __name__ == "__main__":
    main()
