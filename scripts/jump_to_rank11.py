from pathlib import Path

HOME = Path("site/index.html")
TRENDS = Path("site/trends/index.html")


def main():
    if TRENDS.exists():
        text = TRENDS.read_text(encoding="utf-8")
        text = text.replace(
            '<div class="divider">11位〜50位</div>',
            '<div class="divider" id="rank-11" style="scroll-margin-top:16px">11位〜50位</div>',
            1,
        )
        TRENDS.write_text(text, encoding="utf-8")

    if HOME.exists():
        text = HOME.read_text(encoding="utf-8")
        text = text.replace(
            '<a class="home-rank-all" href="trends/">ランキング1位〜10位を詳しく見る →</a>',
            '<a class="home-rank-all" href="trends/#rank-11">11位〜50位を見る →</a>',
            1,
        )
        HOME.write_text(text, encoding="utf-8")

    print("Homepage ranking continuation now jumps directly to rank 11")


if __name__ == "__main__":
    main()
