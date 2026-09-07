from pathlib import Path

PAGE = Path("site/products/index.html")

SNIPPET = r'''
<script id="trend-conversion-tracking">
(() => {
  let source = '';
  let trendQuery = '';
  let trendLabel = '';
  let trendRank = '';

  document.addEventListener('click', (event) => {
    const chip = event.target.closest('.chip[data-q]');
    if (chip) {
      source = 'trend_chip';
      trendQuery = chip.dataset.q || '';
      trendLabel = (chip.textContent || '').trim().replace(/\s+/g, ' ').slice(0, 80);
      trendRank = chip.dataset.trendRank || '';
      if (typeof window.gtag === 'function') {
        window.gtag('event', 'trend_chip_click', {
          trend_query: trendQuery,
          trend_label: trendLabel,
          trend_rank: trendRank,
          page_path: location.pathname
        });
      }
      return;
    }

    const searchButton = event.target.closest('#searchBtn');
    if (searchButton) {
      source = 'typed_search';
      trendQuery = '';
      trendLabel = '';
      trendRank = '';
      return;
    }

    const resultLink = event.target.closest('.product-result-link');
    if (resultLink && source === 'trend_chip' && typeof window.gtag === 'function') {
      window.gtag('event', 'trend_to_rakuten_click', {
        trend_query: trendQuery,
        trend_label: trendLabel,
        trend_rank: trendRank,
        product_id: resultLink.dataset.id || '',
        shipping_included_price: Number(resultLink.dataset.shippingPrice || 0),
        page_path: location.pathname
      });
    }
  }, true);

  const input = document.getElementById('q');
  input?.addEventListener('input', () => {
    source = 'typed_search';
    trendQuery = '';
    trendLabel = '';
    trendRank = '';
  });
})();
</script>
'''


def main():
    if not PAGE.exists():
        print('Product page unavailable; skipping trend conversion tracking')
        return
    text = PAGE.read_text(encoding='utf-8')
    if 'id="trend-conversion-tracking"' in text:
        print('Trend conversion tracking already present')
        return
    if '</body>' not in text:
        raise SystemExit('Malformed product page')
    text = text.replace('</body>', SNIPPET + '\n</body>', 1)
    PAGE.write_text(text, encoding='utf-8')
    print('Added trend chip -> Rakuten conversion tracking')


if __name__ == '__main__':
    main()
