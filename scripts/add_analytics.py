"""Inject optional Google Analytics 4 tracking into the generated static site.

The site builds normally when GA_MEASUREMENT_ID is not configured. When the
variable is present, this script adds GA4 page-view tracking plus explicit
`affiliate_click` and `top_pick_click` events.
"""
from __future__ import annotations

import html
import os
from pathlib import Path

SITE_FILE = Path("site/index.html")
MEASUREMENT_ID = os.environ.get("GA_MEASUREMENT_ID", "").strip()


def main() -> None:
    if not SITE_FILE.exists():
        raise SystemExit(f"Missing generated site: {SITE_FILE}")

    if not MEASUREMENT_ID:
        print("GA_MEASUREMENT_ID is not configured; analytics injection skipped.")
        return

    safe_id = html.escape(MEASUREMENT_ID, quote=True)
    markup = SITE_FILE.read_text(encoding="utf-8")

    if "data-daily-cost-ga4" in markup:
        print("GA4 tracking already present; skipping duplicate injection.")
        return

    head_snippet = f"""
  <!-- Google Analytics 4 (optional) -->
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

  document.querySelectorAll('.buy-button').forEach((button) => {
    button.addEventListener('click', () => {
      const card = button.closest('.product-card');
      const section = button.closest('.category-section');
      const product = cleanText(card?.querySelector('h3'));
      const rank = cleanText(card?.querySelector('.rank-badge'));
      const unitPrice = cleanText(card?.querySelector('.unit-price'));
      gtag('event', 'affiliate_click', {
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
      gtag('event', 'top_pick_click', {
        category_label: cleanText(card.querySelector('.top-pick-category')).slice(0, 80),
        unit_price_label: cleanText(card.querySelector('strong')).slice(0, 40),
        destination: card.getAttribute('href') || ''
      });
    });
  });
})();
</script>
"""

    if "</head>" not in markup or "</body>" not in markup:
        raise SystemExit("Generated HTML is missing </head> or </body>.")

    markup = markup.replace("</head>", head_snippet + "\n</head>", 1)
    markup = markup.replace("</body>", body_snippet + "\n</body>", 1)
    SITE_FILE.write_text(markup, encoding="utf-8")
    print(f"Injected GA4 tracking for {MEASUREMENT_ID}.")


if __name__ == "__main__":
    main()
