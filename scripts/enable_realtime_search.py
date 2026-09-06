from pathlib import Path

PAGE = Path("site/products/index.html")
API = "https://daily-cost-api.netlify.app/api/product-search"
BEST_API = "https://daily-cost-api.netlify.app/api/best-offer"

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
  .realtime-note{font-size:11px;color:#5f6368;margin:4px 0 8px}
  .load-more{display:none;width:100%;min-height:46px;margin:14px 0 6px;border:1px solid #d8d1cb;border-radius:13px;background:#fff;color:#252525;font-weight:800;font-size:13px}
  .load-more:disabled{opacity:.55}
  .retry-btn,.offer-btn{margin-top:9px;border:1px solid #b3261e;border-radius:10px;background:#fff;color:#b3261e;padding:10px 12px;font-weight:800;width:100%;font-size:12px}
  .offer-btn:disabled{opacity:.55}
  .offer-box{margin-top:9px;padding:10px 11px;border-radius:11px;background:#fff5f3;border:1px solid #efd3cf;font-size:11px;line-height:1.55}
  .offer-box strong{display:block;color:#b3261e;font-size:20px;line-height:1.25;margin:2px 0}
  .offer-link{display:flex;align-items:center;justify-content:center;min-height:38px;margin-top:8px;border-radius:9px;background:#b3261e;color:#fff;text-decoration:none;font-weight:800}
  .price small{display:block;margin-top:2px;line-height:1.35}
</style>
"""

script = f"""
{extra_css}
<script>
(() => {{
  const API = {API!r};
  const BEST_API = {BEST_API!r};
  let currentTerm = '';
  let currentPage = 1;
  let pageCount = 1;
  let liveRows = [];

  const loadMore = document.createElement('button');
  loadMore.type = 'button';
  loadMore.id = 'loadMore';
  loadMore.className = 'load-more';
  loadMore.textContent = 'さらに表示';
  results.insertAdjacentElement('afterend', loadMore);

  const note = document.createElement('div');
  note.className = 'realtime-note';
  note.textContent = 'まず製品候補を検索し、気になる製品は「送料込み最安値を調べる」で現在の購入候補を確認できます。';
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

  async function lookupBestOffer(p, holder, button) {{
    button.disabled = true;
    button.textContent = '送料込み最安値を確認中…';
    holder.innerHTML = '';
    try {{
      const url = `${{BEST_API}}?jan=${{encodeURIComponent(p.product_code || '')}}&name=${{encodeURIComponent(p.name || '')}}`;
      const response = await fetch(url, {{method:'GET', mode:'cors'}});
      if (!response.ok) throw new Error(`HTTP ${{response.status}}`);
      const data = await response.json();
      const best = data && data.best;
      if (!best || !best.price || !best.url) {{
        holder.innerHTML = '<div class="offer-box">送料込みの購入候補を特定できませんでした。下の楽天価格ナビで最新情報を確認してください。</div>';
      }} else {{
        holder.innerHTML = `<div class="offer-box">送料込みで見つかった現在の最安候補<strong>${{yen(best.price)}}</strong>${{esc(best.shop || '')}}${{best.point_rate > 1 ? ` ・ ポイント${{best.point_rate}}倍` : ''}}<a class="offer-link" href="${{esc(best.url)}}" target="_blank" rel="nofollow sponsored noopener">この価格で楽天へ</a></div>`;
        holder.querySelector('.offer-link')?.addEventListener('click', () => {{
          if (typeof window.gtag === 'function') window.gtag('event','best_offer_click',{{product_id:p.product_id,price:best.price,shop:best.shop || ''}});
        }});
      }}
      if (typeof window.gtag === 'function') window.gtag('event','best_offer_lookup',{{product_id:p.product_id,matched_by:data.matched_by || '',offer_count:Number(data.count || 0)}});
    }} catch (err) {{
      console.error('Best offer lookup failed', err);
      holder.innerHTML = '<div class="offer-box">現在価格を取得できませんでした。少し時間をおいてもう一度お試しください。</div>';
    }} finally {{
      button.disabled = false;
      button.textContent = '送料込み最安値をもう一度調べる';
    }}
  }}

  function decorateCards() {{
    const cards = Array.from(results.querySelectorAll('.card'));
    cards.forEach((el, index) => {{
      const p = liveRows[index];
      if (!p) return;
      const price = el.querySelector('.price');
      if (price) price.innerHTML = `${{yen(p.min_price)}} <small>参考商品価格（送料別の場合あり）</small>`;
      const oldLink = el.querySelector('.product-result-link');
      if (oldLink) oldLink.textContent = '楽天価格ナビでこの製品を確認';
      if (el.querySelector('.offer-btn')) return;
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'offer-btn';
      button.textContent = '送料込み最安値を調べる';
      const holder = document.createElement('div');
      holder.className = 'offer-holder';
      if (oldLink) {{
        oldLink.insertAdjacentElement('beforebegin', holder);
        holder.insertAdjacentElement('beforebegin', button);
      }} else {{
        el.appendChild(button); el.appendChild(holder);
      }}
      button.addEventListener('click', () => lookupBestOffer(p, holder, button));
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

  const initialTerm = new URLSearchParams(location.search).get('q');
  if (initialTerm) liveSearch(initialTerm, false);
}})();
</script>
"""

html = html.replace("</body>", script + "\n</body>")
PAGE.write_text(html, encoding="utf-8")
print("Realtime product search enabled")
