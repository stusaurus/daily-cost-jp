"""Link existing product-name searches to the exact verified pack on its category page."""
import html


def anchor(jan, count):
    return f"compare-{jan}-{count}"


def add_finder(markup, selected):
    marker = 'id="verified-marketplace-results"'
    if marker in markup:
        return markup
    links = []
    for category, groups in selected.items():
        for product, count, offers in groups:
            if any(offer.total is None for offer in offers):
                continue
            title = product.label if product.label_includes_quantity else f"{product.label} {product.display_amount} × {count}"
            links.append(f'<li data-jan="{product.jan}"><a href="/daily-cost-jp/categories/{category}/'
                         f'#{anchor(product.jan, count)}">{html.escape(title)}</a></li>')
    # This same input handles direct searches and bookmarked ?q= links.
    section = ('<section id="verified-marketplace-results" hidden aria-labelledby="verified-marketplace-heading">'
               '<h2 id="verified-marketplace-heading">楽天市場・Yahoo!ショッピングの送料込み比較</h2>'
               '<ul>' + ''.join(links) + '</ul></section>')
    script = """<script>(() => {
      const input = document.getElementById('q');
      const section = document.getElementById('verified-marketplace-results');
      const rows = Array.from(section.querySelectorAll('li'));
      const fold = value => value.normalize('NFKC').toLowerCase().replace(/\\s+/g, '');
      const names = rows.map(row => fold(row.textContent + row.dataset.jan));
      function filter() {
        const tokens = input.value.trim().normalize('NFKC').split(/\\s+/).map(fold).filter(Boolean);
        let found = 0;
        rows.forEach((row, index) => {
          row.hidden = !tokens.length || !tokens.every(token => names[index].includes(token));
          if (!row.hidden) found++;
        });
        section.hidden = !found;
      }
      input.addEventListener('input', filter);
      document.addEventListener('click', () => requestAnimationFrame(filter));
      window.addEventListener('pageshow', filter);
      filter();
    })();</script>"""
    if markup.count('</main>') != 1 or 'id="q"' not in markup:
        raise ValueError("Marketplace finder search anchor changed")
    # Place matched cross-marketplace offers next to the input, before results from the live API.
    if markup.count('id="status"') != 1:
        raise ValueError("Marketplace finder results anchor changed")
    position = markup.rfind('<', 0, markup.index('id="status"'))
    return markup[:position] + section + script + markup[position:]
