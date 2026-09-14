// Embedded in the head, before GA4 config and before feature event handlers.
(() => {
  const ROOT = '/daily-cost-jp/';
  const TEST_KEY = 'daily_cost_operator_test_v1';
  const NAV_KEY = 'daily_cost_feature_navigation_v1';
  const TTL = 30 * 60 * 1000;
  const allowed = new Set(['product_search', 'buy_judge', 'top_pick', 'category', 'trend', 'daily_pick', 'ranking', 'other']);
  const params = new URLSearchParams(location.search);
  let operator = false;
  try { operator = localStorage.getItem(TEST_KEY) === '1'; } catch (_) {}
  if (params.get('test') === '1' || params.get('test') === '0') {
    operator = params.get('test') === '1';
    try {
      if (operator) localStorage.setItem(TEST_KEY, '1');
      else localStorage.removeItem(TEST_KEY);
    } catch (_) {}
    // Do not leak the test switch through copied URLs or campaign reports.
    const url = new URL(location.href);
    url.searchParams.delete('test');
    try { history.replaceState(history.state, '', url.href); } catch (_) {}
  }
  const isProducts = location.pathname === ROOT + 'products/';
  let inherited = '';
  try {
    const nav = JSON.parse(sessionStorage.getItem(NAV_KEY) || 'null');
    sessionStorage.removeItem(NAV_KEY);
    if (nav && nav.target === location.pathname + location.search &&
        Date.now() - nav.at >= 0 && Date.now() - nav.at < TTL && allowed.has(nav.source)) inherited = nav.source;
  } catch (_) {}
  let searchSource = inherited || 'product_search';
  let resultSource = searchSource;
  let resultTerm = params.get('q') || '';
  const categorySources = new Map();
  const readText = (node) => (node?.textContent || '').trim().replace(/\s+/g, ' ');
  const original = window.gtag;
  // Preserve all legacy events, including direct calls outside the GA injector.
  window.gtag = function(command, name, values) {
    if (command === 'event') {
      const data = { ...(values || {}) };
      if (operator) data.operator_test = '1';
      else delete data.operator_test;
      if (name === 'buy_judge' && data.category_id) {
        categorySources.set(data.category_id, { source: 'buy_judge', at: Date.now() });
      }
      if (name === 'realtime_product_search') {
        resultSource = searchSource;
        resultTerm = data.search_term || '';
      }
      return original('event', name, data);
    }
    return original.apply(this, arguments);
  };
  // Covers GA4 automatic events/page_view as well as explicit feature events.
  if (operator) window.gtag('set', { operator_test: '1' });

  function navigationSource(link) {
    if (link.closest('.top-pick')) return 'top_pick';
    if (link.closest('#buy-judge')) return 'buy_judge';
    if (link.closest('#today-deals-entry, .today-category-link')) return 'daily_pick';
    if (link.closest('.home-rank-first, .home-rank-item, .home-rank-all, #product-ranking-cta') ||
        (location.pathname.includes('/trends/') && link.closest('.card'))) return 'ranking';
    if (link.closest('.category-page-link, .category-search-cta')) {
      const category = new URL(link.href, location.href).pathname.match(/\/categories\/([^/]+)/)?.[1];
      const previous = categorySources.get(category);
      if (previous && Date.now() - previous.at < TTL) return previous.source;
      return inherited || 'category';
    }
    if (location.pathname.includes('/today/')) return 'daily_pick';
    if (location.pathname.includes('/categories/')) return inherited || 'category';
    if (location.pathname.includes('/trends/')) return 'trend';
    return '';
  }
  function isRakuten(link) {
    try {
      const url = new URL(link.href);
      return /^https?:$/.test(url.protocol) &&
        (url.hostname === 'rakuten.co.jp' || url.hostname.endsWith('.rakuten.co.jp'));
    } catch (_) { return false; }
  }
  function sourceFor(link) {
    if (link.matches('[data-exact-rakuten]')) return 'same_product_compare';
    if (link.matches('.product-result-link')) return resultSource;
    const direct = navigationSource(link);
    if (direct) return direct;
    const category = link.closest('.category-section')?.id;
    const previous = categorySources.get(category);
    if (previous && Date.now() - previous.at < TTL) return previous.source;
    if (category || link.closest('.product-card')) return 'category';
    return 'other';
  }
  // Capture intent before the existing chip/search handlers stop propagation.
  document.addEventListener('click', (event) => {
    const target = event.target.closest ? event.target : event.target.parentElement;
    if (!target) return;
    if (isProducts && target.closest('.chip[data-q]')) searchSource = 'trend';
    else if (isProducts && target.closest('#searchBtn')) searchSource = 'product_search';
    const link = target.closest('a[href]');
    if (!link || isRakuten(link)) return;
    try {
      const url = new URL(link.href, location.href);
      if (url.origin !== location.origin || !url.pathname.startsWith(ROOT)) return;
      const source = navigationSource(link);
      if (url.pathname === location.pathname && url.search === location.search && url.hash) {
        if (source) categorySources.set(decodeURIComponent(url.hash.slice(1)), { source, at: Date.now() });
      } else {
        // Exact next destination, consumed once; unrelated navigation clears it.
        sessionStorage.setItem(NAV_KEY, JSON.stringify({ source: source || 'product_search', target: url.pathname + url.search, at: Date.now() }));
      }
    } catch (_) {}
  }, true);
  document.addEventListener('keydown', (event) => {
    if (isProducts && event.key === 'Enter' && event.target.id === 'q') searchSource = 'product_search';
  }, true);

  function affiliate(event) {
    if (event.type === 'auxclick' && event.button !== 1) return;
    const target = event.target.closest ? event.target : event.target.parentElement;
    const link = target?.closest('a[href]');
    if (!link || !isRakuten(link)) return;
    const card = link.closest('.product-card, .deal-card, .card');
    const category = link.closest('.category-section')?.id || location.pathname.match(/\/categories\/([^/]+)/)?.[1] || '';
    window.gtag('event', 'affiliate_click', {
      ...(window.dailyCostTrafficContext || {}),
      affiliate: 'rakuten', conversion_source: sourceFor(link),
      category_id: category,
      product_name: readText(card?.querySelector('h3, h2, .name')).slice(0, 100),
      product_id: link.dataset.id || '',
      rank: readText(card?.querySelector('.rank-badge, .deal-rank, .rank b')),
      unit_price_label: readText(card?.querySelector('.unit-price')).slice(0, 50),
      search_term: link.matches('.product-result-link') ? resultTerm.slice(0, 100) : '',
      shipping_included_price: Number(link.dataset.shippingPrice || 0),
      link_url: link.href, page_path: location.pathname,
      transport_type: 'beacon'
    });
  }
  document.addEventListener('click', affiliate);
  document.addEventListener('auxclick', affiliate);
})();
