from pathlib import Path
import re

PAGE = Path("site/products/index.html")
API = "https://daily-cost-api.kiyo0625puma.workers.dev/api/product-search"

if not PAGE.exists():
    raise SystemExit("site/products/index.html not found")

html = PAGE.read_text(encoding="utf-8")
offer_guard = Path(__file__).with_name("offer_validation.js").read_text(encoding="utf-8")
diagnostics = Path(__file__).with_name("step4_search_diagnostics.js").read_text(encoding="utf-8")
html = html.replace("</head>", '<script id="step4-search-diagnostics">' + diagnostics + '</script><script id="offer-validation">' + offer_guard + '</script>\n</head>', 1)

# The static shell installs a result-click listener too. The realtime listener
# below replaces it and retains the same event with verified shipping details.
html, removed = re.subn(
    r"results\.addEventListener\('click',e=>\{const a=e\.target\.closest\('\.product-result-link'\);if\(a&&typeof window\.gtag==='function'\)window\.gtag\('event','product_result_click',\{product_id:a\.dataset\.id,search_term:q\.value\.trim\(\)\}\);\}\);",
    '', html,
)
if removed != 1:
    raise SystemExit('Expected exactly one static product-result listener to replace')

html = html.replace("<span class=\"eyebrow\">毎朝自動更新</span>", "<span class=\"eyebrow\">楽天からリアルタイム検索</span>")
html = html.replace("本日の検索対象：0製品", "商品名を入力して検索してください")
html = html.replace("本日の検索対象：", "今日のおすすめ：")
html = html.replace(
    "※表示する「最低価格」は楽天の商品価格ナビ製品検索APIの購入可能な最低価格（中古を除く値を優先）です。送料・クーポン・ポイント条件は含めていないため、最終的な支払額はリンク先で必ず確認してください。",
    "※送料込み価格は販売条件を確認できた候補に限り表示します。容量や個数を選ぶ商品は、楽天で購入条件と総額を確認してください。クーポン・ポイント還元は表示価格に含めていません。"
)
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
  .card .img{position:relative}
  .listing-image-badge{position:absolute;left:4px;bottom:4px;padding:2px 5px;border-radius:999px;background:rgba(37,37,37,.82);color:#fff;font-size:8px;font-weight:800;line-height:1.4;white-space:nowrap}
</style>
"""

script = f"""
{extra_css}
<script>
(() => {{
  const API = {API!r};
  const SHIPPING_API = API.replace('/api/product-search', '/api/shipping-lookup');
  const VERIFIED_SHIPPING_FALLBACK = 'https://daily-cost-api.stuffedsaurus.workers.dev/api/shipping-lookup';
  const FALLBACK_LIMIT = 20;
  const LOOKUP_BUDGET_MS = 90000;
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
  note.textContent = '表示価格は、楽天市場で「送料込み／送料無料」と確認できた同一商品の候補だけを表示します。価格確認済みの商品は、実際にリンクする楽天市場の購入候補画像を表示します。まとめ検索で確認できない商品は、JANコードなどを使って順番に追加確認します。';
  status.insertAdjacentElement('afterend', note);
  const recovery = document.createElement('section');
  recovery.id = 'search-recovery';
  recovery.className = 'realtime-note';
  recovery.hidden = true;
  recovery.innerHTML = '<strong>商品名をもう少し詳しくする</strong><p>容量・個数・本体／詰め替えを追加して再検索できます。買う量や単価から選びたい場合は、掲載中の比較ページへ進めます。ブランド・容量は各商品でご確認ください。</p><nav aria-label="買う量から比較する" class="lab-actions"><a class="lab-button secondary" href="../categories/laundry/">洗濯洗剤を比較</a><a class="lab-button secondary" href="../categories/tissue/">ティッシュを比較</a><a class="lab-button secondary" href="../categories/toilet-paper/">トイレットペーパーを比較</a></nav>';
  note.insertAdjacentElement('afterend', recovery);

  function setBusy(on) {{
    document.getElementById('searchBtn').disabled = on;
    loadMore.disabled = on;
  }}

  const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  async function fetchSearchJson(url, timeoutMs) {{
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {{
      const response = await fetch(url, {{method:'GET',mode:'cors',signal:controller.signal}});
      if (!response.ok) throw new Error('API_UNAVAILABLE');
      return await response.json();
    }} finally {{ clearTimeout(timer); }}
  }}

  async function fetchPage(term, page) {{
    const searchTerm = term.replace(/ティッシュペーパー|ティシュー/g, 'ティッシュ');
    const url = `${{API}}?q=${{encodeURIComponent(searchTerm)}}&page=${{page}}&hits=30`;
    return fetchSearchJson(url, 20000);
  }}

  async function fetchShippingFallback(p, deadline) {{
    const params = new URLSearchParams();
    if (p.product_code) params.set('code', p.product_code);
    if (p.name) params.set('name', p.name);
    if (p.brand) params.set('brand', p.brand);
    // Keep the working legacy product API and its priced offers as primary.
    // The corrected matcher is consulted only when no verified offer exists.
    let normalResponse = false;
    let rejectedOffer = null;
    for (const endpoint of [SHIPPING_API, VERIFIED_SHIPPING_FALLBACK]) {{
      const remaining = deadline - Date.now();
      if (remaining <= 0) return {{found:false,lookup_status:'TIME_LIMIT'}};
      try {{
        const data = await fetchSearchJson(`${{endpoint}}?${{params.toString()}}`, Math.min(12000,remaining));
        if (!data || typeof data.found !== 'boolean' || data.error) continue;
        if (data.found && Number.isFinite(Number(data.shipping_included_price)) && Number(data.shipping_included_price)>0 && data.shipping_included_url) {{
          const verified = window.dailyCostVerifiedOffer({{...p,...data,shipping_lookup_pending:false}});
          if (window.dailyCostSearchDiagnostics.reason(verified)==='PRICED_SAFE') return {{...data,...verified}};
          rejectedOffer = {{offer_type_mismatch:verified.offer_type_mismatch,offer_needs_selection:verified.offer_needs_selection,offer_rejected:window.dailyCostSearchDiagnostics.reason(verified)==='DANGEROUS_EXCLUDED'}};
          normalResponse = true;
        }}
        if (data.found === false) normalResponse = true;
      }} catch (err) {{ console.warn('Shipping endpoint unavailable'); }}
    }}
    return {{found:false,...rejectedOffer,lookup_status:Date.now()>=deadline?'TIME_LIMIT':normalResponse?'UNVERIFIED':'API_FAILURE'}};
  }}

  function liveCard(p) {{
    const avg = p.average_price ? `平均 ${{yen(p.average_price)}}` : '平均価格なし';
    const sellers = p.seller_count ? `${{p.seller_count}}店舗で購入可` : '販売数情報なし';
    const review = p.review_count ? `★ ${{Number(p.review_average || 0).toFixed(2)}}（${{Number(p.review_count).toLocaleString('ja-JP')}}件）` : 'レビュー情報なし';
    const includedPrice = Number(p.shipping_included_price || 0);
    const targetUrl = includedPrice > 0 && p.shipping_included_url ? p.shipping_included_url : p.url;
    const listingImage = includedPrice > 0 && p.shipping_included_image ? p.shipping_included_image : '';
    const displayImage = listingImage || p.image || '';
    const imageBadge = listingImage ? '<span class="listing-image-badge">楽天購入候補</span>' : '';
    let priceHtml;
    let detail;
    let button;

    if (includedPrice > 0) {{
      const shop = p.shipping_included_shop ? `・${{esc(p.shipping_included_shop)}}` : '';
      const quantity = p.sale_quantity_label ? `${{esc(p.sale_quantity_label)}}・` : '商品価格 ';
      priceHtml = `${{quantity}}${{yen(includedPrice)}} <small>（送料込み）</small>`;
      detail = `<div class="shipping-price-note">${{shop ? shop.slice(1) : '楽天市場で確認できた購入候補'}}</div>`;
      button = '楽天でこの商品の最新価格を見る';
    }} else if (p.shipping_lookup_pending) {{
      priceHtml = '<span class="shipping-price-pending">送料込み価格を追加確認中…</span>';
      detail = '<div class="shipping-price-note">JANコードなどで同一商品を確認しています</div>';
      button = '楽天で価格を確認';
    }} else {{
      priceHtml = '<span class="shipping-price-unavailable">送料込み価格を取得できません</span>';
      detail = `<div class="shipping-price-note">${{p.offer_type_mismatch ? '用途・タイプが一致する購入候補を確認できないため、価格を表示していません' : p.offer_needs_selection ? '販売数量・選択条件を確認できないため、単一価格を表示していません' : p.shipping_lookup_status==='API_FAILURE' ? '送料確認APIに接続できませんでした。時間をおいて再検索してください' : p.shipping_lookup_status==='TIME_LIMIT' ? '追加確認が時間内に完了しませんでした。商品がないという意味ではありません' : p.shipping_lookup_status==='UNVERIFIED' ? 'APIは応答しましたが、同一商品の送料込み出品を確認できませんでした' : '価格は楽天サイトでご確認ください'}}</div>`;
      button = '楽天で容量と価格を確認';
    }}

    return `<article class="card" data-product-id="${{esc(p.product_id)}}"><div class="img">${{displayImage ? `<img src="${{esc(displayImage)}}" alt="" width="128" height="128" loading="lazy" decoding="async">` : ''}}${{imageBadge}}</div><div><div class="brand">${{esc(p.brand || '')}}</div><div class="name">${{esc(p.name)}}</div><div class="price">${{priceHtml}}</div>${{detail}}<div class="meta">${{esc(avg)}} ・ ${{esc(sellers)}}<br>${{esc(review)}}${{p.product_code ? `<br>JAN: ${{esc(p.product_code)}}` : ''}}</div><a class="btn product-result-link" data-id="${{esc(p.product_id)}}" data-shipping-price="${{includedPrice || ''}}" href="${{esc(targetUrl)}}" target="_blank" rel="nofollow sponsored noopener">${{button}}</a></div></article>`;
  }}

  function recordSearchDiagnosis(phase, fetchStatus = 'OK', emitEvent = true) {{
    const summary = window.dailyCostSearchDiagnostics.summarize(liveRows, fetchStatus);
    status.dataset.searchDiagnosticStatus = summary.status;
    status.dataset.searchDiagnosticCounts = JSON.stringify(summary.counts);
    let diagnosis = document.getElementById('search-diagnostic-note');
    if (!diagnosis) {{
      diagnosis = document.createElement('p');
      diagnosis.id = 'search-diagnostic-note';
      diagnosis.className = 'realtime-note';
      diagnosis.setAttribute('role', 'status');
      status.insertAdjacentElement('afterend', diagnosis);
    }}
    diagnosis.textContent = window.dailyCostSearchDiagnostics.explanation(summary);
    recovery.hidden = summary.safe_priced_count > 0;
    if (emitEvent && typeof window.gtag === 'function') window.gtag('event', 'purchase_search_diagnostics', window.dailyCostSearchDiagnostics.eventPayload(summary, phase));
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
    // Apply the existing verified-price-first grouping as soon as a safe
    // offer arrives, rather than keeping it below unverified cards until all
    // other lookups finish. No new ranking/selection policy is introduced.
    if (Number(p.shipping_included_price || 0) > 0) renderLive();
    else updateStatus();
  }}

  async function runFallbackLookups(generation) {{
    const deadline = Date.now() + LOOKUP_BUDGET_MS;
    // Only lookup order changes. Result order and matching rules are unchanged.
    // Explicit bottles are checked before bulk/refill offers in broad searches.
    const queue = liveRows.filter((p) => p.shipping_lookup_pending)
      .sort((a,b) => Number(/本体/.test(b.name||''))-Number(/本体/.test(a.name||'')))
      .slice(0, FALLBACK_LIMIT);
    for (let i = 0; i < queue.length; i += 1) {{
      if (generation !== searchGeneration) return;
      const p = queue[i];
      try {{
        const data = await fetchShippingFallback(p, deadline);
        if (generation !== searchGeneration) return;
        const target = liveRows.find((row) => row.product_id === p.product_id);
        if (!target) continue;
        target.shipping_lookup_status = data.lookup_status || '';
        if (!data.found) {{
          for (const flag of ['offer_type_mismatch','offer_needs_selection','offer_rejected']) {{
            if (data[flag] === true) target[flag] = true;
          }}
        }}
        if (data && data.found && Number(data.shipping_included_price || 0) > 0) {{
          target.shipping_included_price = Number(data.shipping_included_price);
          target.shipping_included_url = data.shipping_included_url || target.url;
          target.shipping_included_shop = data.shipping_included_shop || '';
          target.shipping_included_image = data.shipping_included_image || '';
          target.shipping_match_score = Number(data.shipping_match_score || 0);
          target.sale_quantity_label = data.sale_quantity_label || '';
          target.shipping_match_name = data.shipping_match_name || '';
          Object.assign(target, window.dailyCostVerifiedOffer(target));
        }}
        target.shipping_lookup_pending = false;
        patchCard(target.product_id);
        recordSearchDiagnosis('initial', 'OK', false);
      }} catch (err) {{
        if (generation !== searchGeneration) return;
        const target = liveRows.find((row) => row.product_id === p.product_id);
        if (target) {{
          target.shipping_lookup_pending = false;
          target.shipping_lookup_status = 'API_FAILURE';
          patchCard(target.product_id);
        }}
        console.warn('Shipping fallback failed');
      }}
      if (i < queue.length - 1 && Date.now()<deadline) await wait(Math.min(1150,deadline-Date.now()));
    }}
  }}

  async function liveSearch(term, append = false) {{
    term = String(term || '').trim();
    q.blur();
    if (term.length < 2) {{
      searchGeneration += 1;
      setBusy(false);
      status.textContent = '2文字以上で検索してください。';
      results.innerHTML = '';
      loadMore.style.display = 'none';
      recovery.hidden = true;
      delete status.dataset.searchDiagnosticCounts;
      delete status.dataset.searchDiagnosticStatus;
      const oldDiagnosis = document.getElementById('search-diagnostic-note');
      if (oldDiagnosis) oldDiagnosis.textContent = '2文字以上で検索してください。';
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
      recovery.hidden = true;
      delete status.dataset.searchDiagnosticCounts;
      delete status.dataset.searchDiagnosticStatus;
      const oldDiagnosis = document.getElementById('search-diagnostic-note');
      if (oldDiagnosis) oldDiagnosis.textContent = '送料・同一商品を確認中です。';
    }} else {{
      status.textContent = `「${{currentTerm}}」の追加候補を確認中…`;
    }}

    setBusy(true);
    try {{
      const data = await fetchPage(currentTerm, currentPage);
      // Enter can start another query while an earlier fetch is in flight.
      // Never render the earlier query's prices/URLs under the new query label.
      if (generation !== searchGeneration) return;
      if (!data || !Array.isArray(data.products)) throw new Error('INVALID_API_RESPONSE');
      let rows = data.products.map(window.dailyCostVerifiedOffer);
      let fallbackCount = 0;
      rows = rows.map((p) => {{
        const needsFallback = !Number(p.shipping_included_price || 0) && fallbackCount < FALLBACK_LIMIT;
        if (needsFallback) fallbackCount += 1;
        return {{ ...p, shipping_lookup_pending: needsFallback, shipping_lookup_status: !Number(p.shipping_included_price||0)&&!needsFallback?'NOT_ATTEMPTED':'' }};
      }});
      liveRows = append ? liveRows.concat(rows) : rows;
      pageCount = Math.max(1, Number(data.page_count || 1));
      renderLive();
      recordSearchDiagnosis('initial');
      runFallbackLookups(generation).then(() => {{
        if (generation === searchGeneration) recordSearchDiagnosis('final');
      }});
      if (typeof window.gtag === 'function') window.gtag('event', 'realtime_product_search', {{
        search_term: currentTerm,
        result_count: liveRows.length,
        shipping_priced_count: liveRows.filter((p) => Number(p.shipping_included_price || 0) > 0).length,
        page: currentPage
      }});
    }} catch (err) {{
      if (generation !== searchGeneration) return;
      console.error('Realtime product search failed');
      recordSearchDiagnosis('final', 'API_FAILURE');
      if (!append) {{
        status.textContent = '楽天のリアルタイム検索に接続できませんでした。';
        results.innerHTML = '<div class="empty">少し時間をおいて、もう一度検索してください。<br><button class="retry-btn" id="retryRealtime" type="button">もう一度検索</button></div>';
        document.getElementById('retryRealtime')?.addEventListener('click', () => liveSearch(currentTerm, false));
      }}
      loadMore.style.display = 'none';
    }} finally {{
      if (generation === searchGeneration) setBusy(false);
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
print("Realtime product search with matched Rakuten listing images enabled")
