import re
from pathlib import Path

PRODUCTS = Path("site/products/index.html")


def main():
    if not PRODUCTS.exists():
        print("Product search page unavailable; skipping realtime UX improvements")
        return

    text = PRODUCTS.read_text(encoding="utf-8")

    text = text.replace(
        "まとめ検索で確認できない商品は、JANコードなどを使って順番に追加確認します。",
        "まとめ検索で確認できない商品は、JANコード・商品名・容量などを使って順番に追加確認します。",
    )
    text = text.replace(
        "JANコードなどで同一商品を確認しています",
        "JANコード・商品名・容量などで同一商品を確認しています",
    )

    helper = '''  function resultBucket(p) {
    if (Number(p.shipping_included_price || 0) > 0) return 0;
    if (p.shipping_lookup_pending) return 1;
    return 2;
  }

  function sortLiveRows() {
    // Keep the API's relative order within each group, but always show verified
    // shipping-inclusive prices before pending/unverified candidates.
    liveRows.sort((a, b) => resultBucket(a) - resultBucket(b));
  }

'''
    if "function resultBucket(p)" not in text:
        text = text.replace("  function updateStatus() {", helper + "  function updateStatus() {", 1)

    text = text.replace(
        "  function renderLive() {\n    updateStatus();",
        "  function renderLive() {\n    sortLiveRows();\n    updateStatus();",
        1,
    )

    if "shipping_lookup_complete" not in text:
        pattern = re.compile(
            r"(  async function runFallbackLookups\(generation\) \{.*?)(\n  \}\n\n  async function liveSearch)",
            re.DOTALL,
        )
        match = pattern.search(text)
        if match:
            completion = '''
    if (generation !== searchGeneration) return;
    sortLiveRows();
    renderLive();
    if (typeof window.gtag === 'function') window.gtag('event', 'shipping_lookup_complete', {
      search_term: currentTerm,
      result_count: liveRows.length,
      shipping_priced_count: liveRows.filter((p) => Number(p.shipping_included_price || 0) > 0).length,
      unverified_count: liveRows.filter((p) => !Number(p.shipping_included_price || 0)).length
    });'''
            text = text[:match.start()] + match.group(1) + completion + match.group(2) + text[match.end():]
        else:
            raise SystemExit("Could not locate fallback lookup function for UX patch")

    # The realtime result link goes straight to Rakuten, so record it as both a
    # product-result click and an affiliate click with an explicit source. This
    # lets GA4 compare revenue intent from product search against other tools.
    if "conversion_source: 'product_search'" not in text:
        old = """      shipping_included_price: Number(a.dataset.shippingPrice || 0)\n    });"""
        new = """      shipping_included_price: Number(a.dataset.shippingPrice || 0)\n    });\n    if (a && typeof window.gtag === 'function') window.gtag('event', 'affiliate_click', {\n      affiliate: 'rakuten',\n      conversion_source: 'product_search',\n      product_id: a.dataset.id || '',\n      search_term: currentTerm,\n      shipping_included_price: Number(a.dataset.shippingPrice || 0),\n      link_url: a.href\n    });"""
        if old not in text:
            raise SystemExit("Could not locate product_result_click payload for affiliate attribution patch")
        text = text.replace(old, new, 1)

    PRODUCTS.write_text(text, encoding="utf-8")
    print("Realtime search prioritizes verified prices and attributes Rakuten clicks to product_search")


if __name__ == "__main__":
    main()
