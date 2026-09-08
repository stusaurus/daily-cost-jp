"""Inject Google Analytics 4 tracking into every generated HTML page."""
from __future__ import annotations

import html
import os
from pathlib import Path

SITE_DIR = Path("site")
MEASUREMENT_ID = os.environ.get("GA_MEASUREMENT_ID", "").strip()


def inject_file(path: Path, safe_id: str) -> bool:
    markup = path.read_text(encoding="utf-8")
    if "data-daily-cost-ga4" in markup:
        return False
    if "</head>" not in markup or "</body>" not in markup:
        print(f"Skipping malformed HTML: {path}")
        return False

    head_snippet = f"""
  <!-- Google Analytics 4 -->
  <script data-daily-cost-ga4 async src="https://www.googletagmanager.com/gtag/js?id={safe_id}"></script>
  <script data-daily-cost-ga4>
    window.dataLayer = window.dataLayer || [];
    function gtag(){{dataLayer.push(arguments);}}
    gtag('js', new Date());
    gtag('config', '{safe_id}');
  </script>
"""

    body_snippet = """
<script data-daily-cost-ga4>
(() => {
  const cleanText = (node) => node ? node.textContent.trim().replace(/\\s+/g, ' ') : '';
  const send = (name, params = {}) => {
    if (typeof window.gtag !== 'function') return;
    window.gtag('event', name, { ...params, page_path: location.pathname });
  };

  document.querySelectorAll('.buy-button').forEach((button) => {
    button.addEventListener('click', () => {
      const card = button.closest('.product-card');
      const section = button.closest('.category-section');
      const product = cleanText(card?.querySelector('h3'));
      const rank = cleanText(card?.querySelector('.rank-badge'));
      const unitPrice = cleanText(card?.querySelector('.unit-price'));
      send('affiliate_click', {
        affiliate: 'rakuten',
        category_id: section?.id || '',
        product_name: product.slice(0, 100),
        rank: rank,
        unit_price_label: unitPrice.slice(0, 50),
        link_url: button.href
      });
    });
  });

  document.querySelectorAll('.top-pick').forEach((card) => {
    card.addEventListener('click', () => {
      send('top_pick_click', {
        category_label: cleanText(card.querySelector('.top-pick-category')).slice(0, 80),
        unit_price_label: cleanText(card.querySelector('strong')).slice(0, 40),
        destination: card.getAttribute('href') || ''
      });
    });
  });

  document.querySelectorAll('.category-page-link').forEach((link) => {
    link.addEventListener('click', () => {
      send('category_link_click', {
        link_text: cleanText(link).slice(0, 80),
        destination: link.getAttribute('href') || ''
      });
    });
  });

  document.querySelectorAll('.category-search-cta').forEach((link) => {
    link.addEventListener('click', () => {
      const match = location.pathname.match(/\/categories\/([^/]+)\/?$/);
      let searchTerm = '';
      try {
        const target = new URL(link.href, location.href);
        searchTerm = target.searchParams.get('q') || '';
      } catch (_) {}
      send('category_search_click', {
        category_id: match ? match[1] : '',
        search_term: searchTerm.slice(0, 100),
        link_text: cleanText(link).slice(0, 100),
        destination: (link.getAttribute('href') || '').slice(0, 300)
      });
    });
  });

  // Ranking and utility navigation are injected late in the build, so use
  // delegated tracking to cover every generated page and future dynamic cards.
  document.addEventListener('click', (event) => {
    const homeRank = event.target.closest('.home-rank-first, .home-rank-item');
    if (homeRank) {
      const rank = cleanText(homeRank.querySelector('.home-rank-first-badge, .home-rank-no'));
      const name = cleanText(homeRank.querySelector('.home-rank-first-name, .home-rank-name'));
      const href = homeRank.getAttribute('href') || '';
      send('ranking_item_click', {
        placement: 'homepage_top10',
        rank: rank,
        product_name: name.slice(0, 100),
        destination_type: /^https?:/i.test(href) ? 'rakuten' : 'site_search',
        destination: href.slice(0, 300)
      });
    }

    const detailRank = event.target.closest('.card .search, .card .rakuten');
    if (detailRank && location.pathname.includes('/trends/')) {
      const card = detailRank.closest('.card');
      send('ranking_item_click', {
        placement: 'ranking_detail',
        rank: cleanText(card?.querySelector('.rank b')),
        product_name: cleanText(card?.querySelector('.name')).slice(0, 100),
        destination_type: detailRank.classList.contains('rakuten') ? 'rakuten' : 'site_search',
        destination: (detailRank.getAttribute('href') || '').slice(0, 300)
      });
    }

    const continueLink = event.target.closest('.home-rank-all, #product-ranking-cta a');
    if (continueLink) {
      send('ranking_continue_click', {
        placement: continueLink.classList.contains('home-rank-all') ? 'homepage_top10' : 'product_search',
        link_text: cleanText(continueLink).slice(0, 80),
        destination: (continueLink.getAttribute('href') || '').slice(0, 200)
      });
    }

    const backToTop = event.target.closest('#back-to-top');
    if (backToTop) {
      send('back_to_top_click', { scroll_y: Math.round(window.scrollY || 0) });
    }
  });
})();
</script>
"""

    markup = markup.replace("</head>", head_snippet + "\n</head>", 1)
    markup = markup.replace("</body>", body_snippet + "\n</body>", 1)
    path.write_text(markup, encoding="utf-8")
    return True


def main() -> None:
    if not SITE_DIR.exists():
        raise SystemExit(f"Missing generated site directory: {SITE_DIR}")
    if not MEASUREMENT_ID:
        print("GA_MEASUREMENT_ID is not configured; analytics injection skipped.")
        return

    safe_id = html.escape(MEASUREMENT_ID, quote=True)
    files = sorted(SITE_DIR.rglob("*.html"))
    if not files:
        raise SystemExit("No generated HTML files found.")

    changed = sum(1 for path in files if inject_file(path, safe_id))
    print(f"Injected GA4 tracking into {changed}/{len(files)} HTML pages for {MEASUREMENT_ID}.")


if __name__ == "__main__":
    main()
