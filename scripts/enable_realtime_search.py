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
  .retry-btn{margin-top:10px;border:0;border-radius:10px;background:#252525;color:#fff;padding:10px 14px;font-weight:800}
</style>
"""

script = f"""
{extra_css}
<script>
(() => {{
  const API = {API!r};
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
  note.textContent = '商品名・ブランド・JANコードから、楽天で現在取得できる製品候補を検索します。';
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

  function renderLive() {{
    status.textContent = `「${{currentTerm}}」の候補：${{liveRows.length}}件${{pageCount > 1 ? `（全${{pageCount}}ページ）` : ''}}`;
    results.innerHTML = liveRows.length
      ? liveRows.map(card).join('')
      : '<div class="empty">一致する製品が見つかりませんでした。商品名を短くして試してください。</div>';
    loadMore.style.display = currentPage < pageCount ? 'block' : 'none';
  }}

  async function liveSearch(term, append = false) {{
    term = String(term || '').trim();
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
      if (typeof window.gtag === 'function') {{
        window.gtag('event', 'realtime_product_search', {{
          search_term: currentTerm,
          result_count: liveRows.length,
          page: currentPage
        }});
      }}
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

  const initialTerm = new URLSearchParams(location.search).get('q');
  if (initialTerm) liveSearch(initialTerm, false);
}})();
</script>
"""

html = html.replace("</body>", script + "\n</body>")
PAGE.write_text(html, encoding="utf-8")
print("Realtime product search enabled")
