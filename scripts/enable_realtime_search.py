from pathlib import Path

PAGE = Path("site/products/index.html")
API = "https://daily-cost-api.netlify.app/api/product-search"
SHIPPING_API = "https://daily-cost-api.netlify.app/api/shipping-status"

if not PAGE.exists():
    raise SystemExit("site/products/index.html not found")

html = PAGE.read_text(encoding="utf-8")

html = html.replace("<span class=\"eyebrow\">毎朝自動更新</span>", "<span class=\"eyebrow\">楽天からリアルタイム検索</span>")
html = html.replace("本日の検索対象：0製品", "商品名を入力して検索してください")
html = html.replace("本日の検索対象：", "今日のおすすめ：")
html = html.replace(
    "現在は日用品カテゴリから毎朝取得した製品スナップショットを検索しています。",
    "検索時に楽天の商品価格ナビへ問い合わせ、その時点で取得できる製品候補を表示します。"
)
html = html.replace(
    "const initial=new URLSearchParams(location.search).get('q');if(initial)q.value=initial;run();",
    "const initial=new URLSearchParams(location.search).get('q');if(initial)q.value=initial;if(!initial){status.textContent='商品名を入力して検索してください';results.innerHTML='';}"
)

extra_css = """
<style>
  .realtime-note{font-size:11px;color:#5f6368;margin:4px 0 8px;line-height:1.6}
  .load-more{display:none;width:100%;min-height:46px;margin:14px 0 6px;border:1px solid #d8d1cb;border-radius:13px;background:#fff;color:#252525;font-weight:800;font-size:13px}
  .load-more:disabled{opacity:.55}
  .retry-btn{margin-top:10px;border:0;border-radius:10px;background:#252525;color:#fff;padding:10px 14px;font-weight:800}
  .price small{display:block;margin-top:2px;line-height:1.35}
  .shipping-price-loading{font-size:17px;color:#7a6f69;font-weight:800}
  .shipping-price-unavailable{font-size:15px;color:#7a6f69;font-weight:800;line-height:1.35}
  .shipping-price-note{margin-top:4px;font-size:10px;color:#7a6f69;line-height:1.45}
</style>
"""

script = f"""
{extra_css}
<script>
(() => {{
  const API = {API!r};
  const SHIPPING_API = {SHIPPING_API!r};
  let currentTerm = '';
  let currentPage = 1;
  let pageCount = 1;
  let liveRows = [];
  const shippingCache = new Map();
  const shippingQueue = [];
  let shippingQueueBusy = false;

  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

  const loadMore = document.createElement('button');
  loadMore.type = 'button';
  loadMore.id = 'loadMore';
  loadMore.className = 'load-more';
  loadMore.textContent = 'さらに表示';
  results.insertAdjacentElement('afterend', loadMore);

  const note = document.createElement('div');
  note.className = 'realtime-note';
  note.textContent = '価格は「送料込み／送料無料」と楽天APIで確認できる同一商品の最安候補を表示します。送料別商品の送料額はAPIから取得できないため、価格＋送料の全ショップ横断最安と一致しない場合があります。';
  status.insertAdjacentElement('afterend', note);

  function setBusy(on) {{
    document.getElementById('searchBtn').disabled = on;
    loadMore.disabled = on;
  }}

  async function fetchPage(term, page) {{
    const url = `${{API}}?q=${{encodeURIComponent(term)}}&page=${{page}}&hits=30`;
    const response = await fetch(url, {{ method: 'GET', mode: 'cors' }});
    if (!response.ok) throw new Error(`HTTP ${{response.status}}`);
    return response.json();
  }}

  async function fetchShippingBest(p) {{
    const url = `${{SHIPPING_API}}?jan=${{encodeURIComponent(p.product_code || '')}}&price=${{encodeURIComponent(p.min_price || 0)}}&name=${{encodeURIComponent(p.name || '')}}&brand=${{encodeURIComponent(p.brand || '')}}`;
    const response = await fetch(url, {{ method: 'GET', mode: 'cors' }});
    if (!response.ok) return {{included_min_price:null}};
    return response.json();
  }}

  function shippingKey(p) {{
    return p.product_id || `${{p.product_code || ''}}|${{p.name || ''}}`;
  }}

  function applyShippingResult(el, p, data) {{
    const price = el.querySelector('.price');
    const link = el.querySelector('.product-result-link');
    if (!price || !link) return;

    const includedPrice = Number(data && data.included_min_price || 0);
    const includedUrl = String(data && data.included_offer_url || '');
    if (includedPrice > 0) {{
      price.innerHTML = `${{yen(includedPrice)}} <small>送料込み（送料無料）で買える最安値</small>`;
      if (includedUrl) link.href = includedUrl;
      link.textContent = 'この価格で楽天へ';
      let detail = el.querySelector('.shipping-price-note');
      if (!detail) {{
        detail = document.createElement('div');
        detail.className = 'shipping-price-note';
        price.insertAdjacentElement('afterend', detail);
      }}
      detail.textContent = '楽天市場で送料込み／送料無料と確認できた購入候補の最安値';
      link.dataset.shippingPrice = String(includedPrice);
    }} else {{
      price.innerHTML = '<span class="shipping-price-unavailable">送料込み価格を確認できません</span>';
      link.textContent = '楽天で価格＋送料を確認';
      link.dataset.shippingPrice = '';
    }}
  }}

  async function processShippingQueue() {{
    if (shippingQueueBusy) return;
    shippingQueueBusy = true;
    await sleep(1200);
    while (shippingQueue.length) {{
      const {{el, p}} = shippingQueue.shift();
      if (!el.isConnected) continue;
      const key = shippingKey(p);
      try {{
        let data = shippingCache.get(key);
        if (!data) {{
          data = await fetchShippingBest(p);
          shippingCache.set(key, data);
        }}
        applyShippingResult(el, p, data);
        if (typeof window.gtag === 'function') window.gtag('event','shipping_included_price_loaded',{{
          product_id:p.product_id || '',
          search_term:currentTerm,
          included_min_price:Number(data && data.included_min_price || 0),
          matched_by:data && data.matched_by || ''
        }});
      }} catch (err) {{
        console.error('Shipping included price lookup failed', err);
        applyShippingResult(el, p, {{included_min_price:null}});
      }}
      await sleep(1200);
    }}
    shippingQueueBusy = false;
  }}

  function enqueueShippingLookup(el, p) {{
    if (el.dataset.shippingQueued === '1') return;
    el.dataset.shippingQueued = '1';
    const cached = shippingCache.get(shippingKey(p));
    if (cached) {{
      applyShippingResult(el, p, cached);
      return;
    }}
    shippingQueue.push({{el, p}});
    processShippingQueue();
  }}

  function decorateCards() {{
    const cards = Array.from(results.querySelectorAll('.card'));
    const observer = 'IntersectionObserver' in window ? new IntersectionObserver((entries, obs) => {{
      entries.forEach((entry) => {{
        if (!entry.isIntersecting) return;
        const index = Number(entry.target.dataset.liveIndex || -1);
        const p = liveRows[index];
        if (p) enqueueShippingLookup(entry.target, p);
        obs.unobserve(entry.target);
      }});
    }}, {{rootMargin:'250px 0px'}}) : null;

    cards.forEach((el, index) => {{
      const p = liveRows[index];
      if (!p) return;
      el.dataset.liveIndex = String(index);
      const price = el.querySelector('.price');
      if (price) price.innerHTML = '<span class="shipping-price-loading">送料込み最安値を確認中…</span>';
      const link = el.querySelector('.product-result-link');
      if (link) {{
        link.textContent = '楽天で価格＋送料を確認';
      }}
      if (observer) observer.observe(el);
      else enqueueShippingLookup(el, p);
    }});
  }}

  function renderLive() {{
    status.textContent = `「${{currentTerm}}」の候補：${{liveRows.length}}件${{pageCount > 1 ? `（全${{pageCount}}ページ）` : ''}}`;
    results.innerHTML = liveRows.length
      ? liveRows.map(card).join('')
      : '<div class="empty">一致する製品が見つかりませんでした。商品名を短くして試してください。</div>';
    loadMore.style.display = currentPage < pageCount ? 'block' : 'none';
    decorateCards();
  }}

  async function liveSearch(term, append = false) {{
    term = String(term || '').trim();
    q.blur();
    if (term.length < 2) {{
      status.textContent = '2文字以上で検索してください。';
      results.innerHTML = '';
      loadMore.style.display = 'none';
      return;
    }}
    if (!append) {{
      currentTerm = term;
      currentPage = 1;
      liveRows = [];
      shippingQueue.length = 0;
      status.textContent = `「${{term}}」を楽天から検索中…`;
      results.innerHTML = '';
      loadMore.style.display = 'none';
    }}
    setBusy(true);
    try {{
      const data = await fetchPage(currentTerm, currentPage);
      const rows = Array.isArray(data.products) ? data.products : [];
      liveRows = append ? liveRows.concat(rows) : rows;
      pageCount = Math.max(1, Number(data.page_count || 1));
      renderLive();
      if (typeof window.gtag === 'function') window.gtag('event','realtime_product_search',{{search_term:currentTerm,result_count:liveRows.length,page:currentPage}});
    }} catch (err) {{
      console.error('Realtime product search failed', err);
      if (!append) {{
        status.textContent = '楽天のリアルタイム検索に接続できませんでした。';
        results.innerHTML = '<div class="empty">少し時間をおいて、もう一度検索してください。<br><button class="retry-btn" id="retryRealtime" type="button">もう一度検索</button></div>';
        document.getElementById('retryRealtime')?.addEventListener('click', () => liveSearch(currentTerm, false));
      }}
      loadMore.style.display = 'none';
    }} finally {{
      setBusy(false);
    }}
  }}

  document.getElementById('searchBtn').addEventListener('click', (e) => {{e.preventDefault();e.stopImmediatePropagation();liveSearch(q.value, false);}}, true);
  q.addEventListener('keydown', (e) => {{if (e.key === 'Enter') {{e.preventDefault();e.stopImmediatePropagation();liveSearch(q.value, false);}}}}, true);
  document.querySelectorAll('.chip').forEach((b) => {{b.addEventListener('click', (e) => {{e.preventDefault();e.stopImmediatePropagation();q.value=b.dataset.q || '';liveSearch(q.value, false);}}, true);}});
  loadMore.addEventListener('click', async () => {{if (currentPage >= pageCount) return;currentPage += 1;await liveSearch(currentTerm, true);}});

  results.addEventListener('click', (e) => {{
    const a = e.target.closest('.product-result-link');
    if (a && typeof window.gtag === 'function') window.gtag('event','product_result_click',{{
      product_id:a.dataset.id || '',
      search_term:currentTerm,
      shipping_included_price:Number(a.dataset.shippingPrice || 0)
    }});
  }});

  const initialTerm = new URLSearchParams(location.search).get('q');
  if (initialTerm) liveSearch(initialTerm, false);
}})();
</script>
"""

html = html.replace("</body>", script + "\n</body>")
PAGE.write_text(html, encoding="utf-8")
print("Realtime product search enabled")
