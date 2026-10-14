from pathlib import Path

HOME = Path("site/index.html")
TRENDS = Path("site/trends/index.html")


def main():
    rank11_available = False

    if TRENDS.exists():
        text = TRENDS.read_text(encoding="utf-8")
        if 'id="rank-11"' not in text:
            text = text.replace(
                '<div class="divider">11位〜50位</div>',
                '<div class="divider" id="rank-11" style="scroll-margin-top:16px">11位〜50位</div>',
                1,
            )
        rank11_available = 'id="rank-11"' in text
        TRENDS.write_text(text, encoding="utf-8")

    if HOME.exists():
        text = HOME.read_text(encoding="utf-8")
        if rank11_available:
            replacement = '<a class="home-rank-all" href="trends/#rank-11">11位〜50位を見る →</a>'
        else:
            replacement = '<a class="home-rank-all" href="trends/">ランキングを見る →</a>'

        text = text.replace(
            '<a class="home-rank-all" href="trends/">ランキング1位〜10位を詳しく見る →</a>',
            replacement,
            1,
        )
        text = text.replace(
            '<a class="home-rank-all" href="trends/#rank-11">11位〜50位を見る →</a>',
            replacement,
            1,
        )
        HOME.write_text(text, encoding="utf-8")

    print(f"Homepage ranking continuation configured; rank11_available={rank11_available}")


if __name__ == "__main__":
    main()
