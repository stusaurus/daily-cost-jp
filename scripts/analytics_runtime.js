// Embedded in the head, before GA4 config and before feature event handlers.
(() => {
  const ROOT = '/daily-cost-jp/';
  const TEST_KEY = 'daily_cost_operator_test_v1';
  const NAV_KEY = 'daily_cost_feature_navigation_v1';
  const TTL = 30 * 60 * 1000;
  const allowed = new Set(['product_search', 'buy_judge', 'top_pick', 'category', 'trend', 'daily_pick', 'ranking', 'same_product_compare', 'product_guide', 'price_guide', 'other']);
  const params = new URLSearchParams(location.search);
  let operator = false;
  let persistent = true;
  try { operator = localStorage.getItem(TEST_KEY) === '1'; }
  catch (_) { persistent = false; }
  // Some browsers allow reads but reject writes (quota/private storage).
  // Read the tab fallback even when localStorage.getItem itself succeeds.
  if (!operator) {
    try {
      operator = sessionStorage.getItem(TEST_KEY) === '1';
      if (operator) persistent = false;
    } catch (_) {}
  }
  if (params.get('test') === '1' || params.get('test') === '0') {
    operator = params.get('test') === '1';
    try {
      if (operator) localStorage.setItem(TEST_KEY, '1');
      else localStorage.removeItem(TEST_KEY);
    } catch (_) {
      persistent = false;
      try { sessionStorage.setItem(TEST_KEY, operator ? '1' : '0'); } catch (_) {}
    }
    if (!operator) { try { sessionStorage.removeItem(TEST_KEY); } catch (_) {} }
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
  const recentEvents = [];
  function showOperatorStatus() {
    if (!document.body) return;
    let panel = document.getElementById('operator-test-status');
    if (!operator) { panel?.remove(); return; }
    if (!panel) {
      panel = document.createElement('aside');
      panel.id = 'operator-test-status';
      panel.setAttribute('aria-label', '運営者テストの状態');
      panel.style.cssText = 'padding:10px 16px;background:#fff4cc;color:#423514;font:14px/1.6 system-ui;border-bottom:1px solid #ddc777;overflow-wrap:anywhere';
      const label = document.createElement('strong');
      label.textContent = '運営者テスト ON（operator_test=1）';
      panel.append(label);
      const off = document.createElement('button');
      off.type = 'button';
      off.textContent = 'テストを解除';
      off.style.cssText = 'margin-left:12px;min-height:44px;padding:8px 12px;cursor:pointer';
      off.addEventListener('click', () => {
        operator = false;
        try { localStorage.removeItem(TEST_KEY); } catch (_) {}
        try { sessionStorage.removeItem(TEST_KEY); } catch (_) {}
        original('set', { operator_test: '0' });
        showOperatorStatus();
      });
      panel.append(off);
      const details = document.createElement('details');
      const summary = document.createElement('summary');
      summary.textContent = '計測確認（直近のイベント）';
      const note = document.createElement('p');
      note.textContent = 'GA4タグへの送信内容です。GA4側の受信完了を示すものではありません。';
      const list = document.createElement('ul');
      list.id = 'operator-test-events';
      details.append(summary, note, list);
      panel.append(details);
      if (!persistent) {
        const warning = document.createElement('p');
        warning.textContent = 'このブラウザでは設定を長期保存できません。ページ移動後もON表示を確認してください。';
        panel.append(warning);
      }
      document.body.prepend(panel);
    }
    const list = panel.querySelector('#operator-test-events');
    list.replaceChildren(...recentEvents.map(text => {
      const item = document.createElement('li'); item.textContent = text; return item;
    }));
  }
  // Preserve all legacy events, including direct calls outside the GA injector.
  window.gtag = function(command, name, values) {
    if (command === 'event') {
      const data = { ...(values || {}) };
      // An absent value is ambiguous in GA4. Explicit 0/1 applies to every event.
      data.operator_test = operator ? '1' : '0';
      if (name === 'product_result_click') data.conversion_source = resultSource;
      if (name === 'same_product_rakuten_click') data.conversion_source = 'same_product_compare';
      if (name === 'affiliate_click' && !allowed.has(data.conversion_source)) data.conversion_source = 'other';
      if (name === 'buy_judge' && data.category_id) {
        categorySources.set(data.category_id, { source: 'buy_judge', at: Date.now() });
      }
      if (name === 'realtime_product_search') {
        resultSource = searchSource;
        resultTerm = data.search_term || '';
      }
      if (operator) {
        recentEvents.unshift(`${name} | conversion_source=${data.conversion_source || '—'} | operator_test=${data.operator_test}`);
        recentEvents.length = Math.min(recentEvents.length, 6);
        showOperatorStatus();
      }
      return original('event', name, data);
    }
    return original.apply(this, arguments);
  };
  // Covers GA4 automatic events/page_view as well as explicit feature events.
  window.gtag('set', { operator_test: operator ? '1' : '0' });
  document.addEventListener('DOMContentLoaded', showOperatorStatus, { once: true });
  if (document.readyState !== 'loading') showOperatorStatus();
  window.addEventListener('storage', (event) => {
    if (event.key !== TEST_KEY && event.key !== null) return;
    try { operator = localStorage.getItem(TEST_KEY) === '1'; } catch (_) { return; }
    original('set', { operator_test: operator ? '1' : '0' });
    showOperatorStatus();
  });

  function navigationSource(link) {
    const explicit = link.closest('[data-conversion-source]')?.dataset.conversionSource;
    if (allowed.has(explicit)) return explicit;
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
    if (location.pathname.includes('/guides/attack-zero-price/')) return 'product_guide';
    if (location.pathname.includes('/guides/')) return 'price_guide';
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
        const section = document.getElementById(decodeURIComponent(url.hash.slice(1)))?.closest('.category-section');
        if (source && section?.id) categorySources.set(section.id, { source, at: Date.now() });
      } else {
        // Exact next destination, consumed once; unrelated navigation clears it.
        if (source) sessionStorage.setItem(NAV_KEY, JSON.stringify({ source, target: url.pathname + url.search, at: Date.now() }));
        else sessionStorage.removeItem(NAV_KEY);
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
  document.addEventListener('click', affiliate, true);
  document.addEventListener('auxclick', affiliate, true);
})();
