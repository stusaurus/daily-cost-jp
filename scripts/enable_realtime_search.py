from pathlib import Path

PAGE = Path("site/products/index.html")
API = "https://daily-cost-api.netlify.app/api/product-search"

if not PAGE.exists():
    raise SystemExit("site/products/index.html not found")

html = PAGE.read_text(encoding="utf-8")

html = html.replace("<span class=\"eyebrow\">毎朝自動更新</span>", "<span class=\"eyebrow\">楽天からリアルタイム検索</span>")
html = html.replace("本日の検索対象：0製品", "商品名を入力して検索してください")
html = html.replace("本日の検索対象：", "今日のおすすめ：")
html = html.replace(
    "現在は日用品カテゴリから毎朝取得した製品スナップショットを検索しています。",
    "検索時に楽天の商品価格ナビと楽天市場へ問い合わせ、その時点で取得できる製品候補と送料込み価格をまとめて確認します。"
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
  .shipping-price-unavailable{font-size:15px;color:#7a6f69;font-weight:800;line-height:1.35}
  .shipping-price-pending{font-size:15px;color:#7a6f69;font-weight:800;line-height:1.35}
  .shipping-price-note{margin-top:4px;font-size:10px;color:#7a6f69;line-height:1.45}
</style>
"""

script = f"""
{extra_css}
<script>
(() => {{
  const API = {API!r};
  const SHIPPING_API = API.replace('/api/product-search', '/api/shipping-lookup');
  const FALLBACK_LIMIT = 20;
  let currentTerm = '';
  let currentPage = 1;
  let pageCount = 1;
  let liveRows = [];
  let searchGeneration = 0;

  const loadMore = document.createElement('button');
  loadMore.type = 'button';
  loadMore.id = 'loadMore';
  loadMore.className = 'load-more';
  loadMore.textContent = 'さらに表示';
  results.insertAdjacentElement('afterend', loadMore);

  const note = document.createElement('div');
  note.className = 'realtime-note';
  note.textContent = '表示価格は、楽天市場で「送料込み／送料無料」と確認できた同一商品の候補だけを表示します。まとめ検索で確認できない商品は、JANコードなどを使って順番に追加確認します。';
  status.insertAdjacentElement('afterend', note);

  function setBusy(on) {{
    document.getElementById('searchBtn').disabled = on;
    loadMore.disabled = on;
  }}

  const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

  async function fetchPage(term, page) {{
    const url = `${{API}}?q=${{encodeURIComponent(term)}}&page=${{page}}&hits=30`;
    const response = await fetch(url, {{ method: 'GET', mode: 'cors' }});
    if (!response.ok) throw new Error(`HTTP ${{response.status}}`);
    return response.json();
  }}

  async function fetchShippingFallback(p) {{
    const params = new URLSearchParams();
    if (p.product_code) params.set('code', p.product_code);
    if (p.name) params.set('name', p.name);
    if (p.brand) params.set('brand', p.brand);
    const response = await fetch(`${{SHIPPING_API}}?${{params.toString()}}`, {{ method: 'GET', mode: 'cors' }});
    if (!response.ok) throw new Error(`HTTP ${{response.status}}`);
    return response.json();
  }}

  function liveCard(p) {{
    const avg = p.average_price ? `平均 ${{yen(p.average_price)}}` : '平均価格なし';
    const sellers = p.seller_count ? `${{p.seller_count}}店舗で購入可` : '販売数情報なし';
    const review = p.review_count ? `★ ${{Number(p.review_average || 0).toFixed(2)}}（${{Number(p.review_count).toLocaleString('ja-JP')}}件）` : 'レビュー情報なし';
    const includedPrice = Number(p.shipping_included_price || 0);
    const targetUrl = includedPrice > 0 && p.shipping_included_url ? p.shipping_included_url : p.url;
    let priceHtml;
    let detail;
    let button;

    if (includedPrice > 0) {{
      priceHtml = `${{yen(includedPrice)}} <small>送料込み最安値</small>`;
      detail = '<div class="shipping-price-note">楽天市場で送料込み／送料無料と確認できた購入候補</div>';
      button = 'この価格で楽天へ';
    }} else if (p.shipping_lookup_pending) {{
      priceHtml = '<span class="shipping-price-pending">送料込み価格を追加確認中…</span>';
      detail = '<div class="shipping-price-note">JANコードなどで同一商品を確認しています</div>';
      button = '楽天で価格を確認';
    }} else {{
      priceHtml = '<span class="shipping-price-unavailable">送料込み価格を取得できません</span>';
      detail = '<div class="shipping-price-note">価格は楽天サイトでご確認ください</div>';
      button = '楽天で価格を確認';
    }}

    return `<article class="card" data-product-id="${{esc(p.product_id)}}"><div class="img">${{p.image ? `<img src="${{esc(p.image)}}" alt="" loading="lazy">` : ''}}</div><div><div class="brand">${{esc(p.brand || '')}}</div><div class="name">${{esc(p.name)}}</div><div class="price">${{priceHtml}}</div>${{detail}}<div class="meta">${{esc(avg)}} ・ ${{esc(sellers)}}<br>${{esc(review)}}${{p.product_code ? `<br>JAN: ${{esc(p.product_code)}}` : ''}}</div><a class="btn product-result-link" data-id="${{esc(p.product_id)}}" data-shipping-price="${{includedPrice || ''}}" href="${{esc(targetUrl)}}" target="_blank" rel="nofollow sponsored noopener">${{button}}</a></div></article>`;
  }}

  function updateStatus() {{
    const priced = liveRows.filter((p) => Number(p.shipping_included_price || 0) > 0).length;
    const pending = liveRows.filter((p) => p.shipping_lookup_pending).length;
    status.textContent = `「${{currentTerm}}」の候補：${{liveRows.length}}件（送料込み価格確認済み ${{priced}}件${{pending ? `・追加確認中 ${{pending}}件` : ''}}）${{pageCount > 1 ? `・全${{pageCount}}ページ` : ''}}`;
  }}

  function renderLive() {{
    updateStatus();
    results.innerHTML = liveRows.length
      ? liveRows.map(liveCard).join('')
      : '<div class="empty">一致する製品が見つかりませんでした。商品名を短くして試してください。</div>';
    loadMore.style.display = currentPage < pageCount ? 'block' : 'none';
  }}

  function patchCard(productId) {{
    const p = liveRows.find((row) => row.product_id === productId);
    const cardEl = results.querySelector(`[data-product-id="${{CSS.escape(productId)}}"]`);
    if (!p || !cardEl) return;
    cardEl.outerHTML = liveCard(p);
    updateStatus();
  }}

  async function runFallbackLookups(generation) {{
    const queue = liveRows.filter((p) => p.shipping_lookup_pending).slice(0, FALLBACK_LIMIT);
    for (let i = 0; i < queue.length; i += 1) {{
      if (generation !== searchGeneration) return;
      const p = queue[i];
      try {{
        const data = await fetchShippingFallback(p);
        if (generation !== searchGeneration) return;
        const target = liveRows.find((row) => row.product_id === p.product_id);
        if (!target) continue;
        if (data && data.found && Number(data.shipping_included_price || 0) > 0) {{
          target.shipping_included_price = Number(data.shipping_included_price);
          target.shipping_included_url = data.shipping_included_url || target.url;
          target.shipping_included_shop = data.shipping_included_shop || '';
          target.shipping_match_score = Number(data.shipping_match_score || 0);
        }}
        target.shipping_lookup_pending = false;
        patchCard(target.product_id);
      }} catch (err) {{
        const target = liveRows.find((row) => row.product_id === p.product_id);
        if (target) {{
          target.shipping_lookup_pending = false;
          patchCard(target.product_id);
        }}
        console.warn('Shipping fallback failed', err);
      }}
      if (i < queue.length - 1) await wait(1150);
    }}
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

    const generation = append ? searchGeneration : ++searchGeneration;
    if (!append) {{
      currentTerm = term;
      currentPage = 1;
      liveRows = [];
      status.textContent = `「${{term}}」の送料込み価格までまとめて確認中…`;
      results.innerHTML = '';
      loadMore.style.display = 'none';
    }} else {{
      status.textContent = `「${{currentTerm}}」の追加候補を確認中…`;
    }}

    setBusy(true);
    try {{
      const data = await fetchPage(currentTerm, currentPage);
      let rows = Array.isArray(data.products) ? data.products : [];
      let fallbackCount = 0;
      rows = rows.map((p) => {{
        const needsFallback = !Number(p.shipping_included_price || 0) && fallbackCount < FALLBACK_LIMIT;
        if (needsFallback) fallbackCount += 1;
        return {{ ...p, shipping_lookup_pending: needsFallback }};
      }});
      liveRows = append ? liveRows.concat(rows) : rows;
      pageCount = Math.max(1, Number(data.page_count || 1));
      renderLive();
      runFallbackLookups(generation);
      if (typeof window.gtag === 'function') window.gtag('event', 'realtime_product_search', {{
        search_term: currentTerm,
        result_count: liveRows.length,
        shipping_priced_count: liveRows.filter((p) => Number(p.shipping_included_price || 0) > 0).length,
        page: currentPage
      }});
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

  document.getElementById('searchBtn').addEventListener('click', (e) => {{
    e.preventDefault();
    e.stopImmediatePropagation();
    liveSearch(q.value, false);
  }}, true);

  q.addEventListener('keydown', (e) => {{
    if (e.key === 'Enter') {{
      e.preventDefault();
      e.stopImmediatePropagation();
      liveSearch(q.value, false);
    }}
  }}, true);

  document.querySelectorAll('.chip').forEach((b) => {{
    b.addEventListener('click', (e) => {{
      e.preventDefault();
      e.stopImmediatePropagation();
      q.value = b.dataset.q || '';
      liveSearch(q.value, false);
    }}, true);
  }});

  loadMore.addEventListener('click', async () => {{
    if (currentPage >= pageCount) return;
    currentPage += 1;
    await liveSearch(currentTerm, true);
  }});

  results.addEventListener('click', (e) => {{
    const a = e.target.closest('.product-result-link');
    if (a && typeof window.gtag === 'function') window.gtag('event', 'product_result_click', {{
      product_id: a.dataset.id || '',
      search_term: currentTerm,
      shipping_included_price: Number(a.dataset.shippingPrice || 0)
    }});
  }});

  const initialTerm = new URLSearchParams(location.search).get('q');
  if (initialTerm) liveSearch(initialTerm, false);
}})();
</script>
"""

html = html.replace("</body>", script + "\n</body>")
PAGE.write_text(html, encoding="utf-8")
print("Realtime product search with progressive shipping fallback enabled")
