import re
from pathlib import Path

HOME = Path("site/index.html")


def find_section_end(markup: str, section_id: str):
    start_match = re.search(
        rf'<section\b[^>]*\bid="{re.escape(section_id)}"[^>]*>',
        markup,
        flags=re.IGNORECASE,
    )
    if not start_match:
        return None

    depth = 0
    token_re = re.compile(r'<section\b[^>]*>|</section>', flags=re.IGNORECASE)
    for token in token_re.finditer(markup, start_match.start()):
        if token.group(0).lower().startswith('<section'):
            depth += 1
        else:
            depth -= 1
            if depth == 0:
                return token.end()
    return None


def main():
    if not HOME.exists():
        print("Homepage unavailable; skipping ranking move")
        return

    text = HOME.read_text(encoding="utf-8")
    hero_match = re.search(
        r'<style id="home-ranking-hero-style">.*?</style>\s*<section id="home-ranking-hero">.*?</section>',
        text,
        flags=re.DOTALL,
    )
    if not hero_match:
        print("Homepage ranking block not found; skipping")
        return

    hero = hero_match.group(0)
    text_without_hero = text[:hero_match.start()] + text[hero_match.end():]

    insert_at = find_section_end(text_without_hero, "buy-judge")
    if insert_at is None:
        print("Buy checker section not found; keeping current ranking position")
        return

    text = text_without_hero[:insert_at] + "\n" + hero + "\n" + text_without_hero[insert_at:]
    HOME.write_text(text, encoding="utf-8")
    print("Moved homepage TOP10 below product search and buy checker")


if __name__ == "__main__":
    main()
