from pathlib import Path
import re

PAGE = Path("site/index.html")
API = "https://daily-cost-api.kiyo0625puma.workers.dev/api/product-search"
SHIPPING_API = "https://daily-cost-api.kiyo0625puma.workers.dev/api/shipping-lookup"


def section_end(markup: str, start: int) -> int:
    token_re = re.compile(r"</?section\b[^>]*>", re.IGNORECASE)
    depth = 0
    for match in token_re.finditer(markup, start):
        token = match.group(0).lower()
        if token.startswith("</section"):
            depth -= 1
            if depth == 0:
                return match.end()
        else:
            depth += 1
    return -1


if not PAGE.exists():
    raise SystemExit("site/index.html not found")

markup = PAGE.read_text(encoding="utf-8")
if 'id="exact-store-compare"' in markup:
    print("Exact store comparison already present")
    raise SystemExit(0)

css = r'''
.exact-compare{margin:14px 0 20px;padding:16px;border:1px solid #d9e3dc;border-radius:18px;background:linear-gradient(180deg,#f7fff9 0%,#fff 100%);box-shadow:0 5px 18px rgba(34,80,49,.05)}
.exact-kicker{font-size:11px;font-weight:900;color:#22663a;letter-spacing:.03em}.exact-compare h2{font-size:22px;line-height:1.28;margin:3px 0 5px}.exact-lead{margin:0 0 12px;color:#5f6368;font-size:12px;line-height:1.65}.exact-fields{display:grid;grid-template-columns:1fr 120px;gap:8px}.exact-fields input{min-width:0;height:46px;border:1px solid #cfd9d2;border-radius:11px;background:#fff;padding:0 11px;font-size:16px}.exact-fields button{grid-column:1/-1;min-height:46px;border:0;border-radius:11px;background:#22663a;color:#fff;font-size:14px;font-weight:900}.exact-guide{font-size:10px;color:#777;line-height:1.55;margin:8px 0 0}.exact-status{font-size:11px;color:#5f6368;margin-top:10px}.exact-candidates{display:grid;gap:9px;margin-top:10px}.exact-candidate{display:grid;grid-template-columns:70px 1fr;gap:10px;padding:10px;border:1px solid #e0e6e2;border-radius:13px;background:#fff}.exact-img{width:70px;height:70px;border:1px solid #e5e7eb;border-radius:10px;display:grid;place-items:center;overflow:hidden}.exact-img img{width:100%;height:100%;object-fit:contain}.exact-name{font-size:12px;font-weight:800;line-height:1.45;margin-bottom:4px}.exact-brand{font-size:9px;color:#777}.exact-price{font-size:17px;font-weight:900;color:#22663a}.exact-price small{font-size:9px;color:#777}.exact-choose{width:100%;margin-top:7px;min-height:36px;border:0;border-radius:9px;background:#252525;color:#fff;font-size:11px;font-weight:800}.exact-choose:disabled{background:#c4c8c5}.exact-result{display:none;margin-top:12px;padding:14px;border-radius:14px;background:#fff;border:1px solid #d8e4db}.exact-result.show{display:block}.exact-verdict{font-size:20px;font-weight:900;margin-bottom:6px}.exact-result p{font-size:11px;line-height:1.6;margin:4px 0}.exact-rakuten{display:flex;align-items:center;justify-content:center;min-height:42px;margin-top:10px;border-radius:10px;background:#b3261e;color:#fff;text-decoration:none;font-size:12px;font-weight:900}.exact-note{font-size:9px!important;color:#777}.exact-loading{padding:13px;border:1px dashed #ccd6cf;border-radius:12px;background:#fff;font-size:11px;color:#666}
@media(max-width:420px){.exact-fields{grid-template-columns:1fr 105px}}
'''
markup = markup.replace("</style>", css + "\n</style>", 1)

section = f'''
<section class="exact-compare" id="exact-store-compare" aria-label="同じ商品の店頭価格と楽天価格を比較">
  <div class="exact-kicker">同じ商品で比較</div>
  <h2>店頭と楽天、どっちが安い？</h2>
  <p class="exact-lead">商品名と店頭価格を入れて、画像・容量を見ながら<strong>同じ商品</strong>を選ぶと、楽天の送料込み価格とその場で比較します。</p>
  <div class="exact-fields">
    <input id="exact-name" type="search" enterkeyhint="search" placeholder="例：アリエール ジェルボール 39個">
    <input id="exact-store-price" type="number" inputmode="decimal" min="1" step="1" placeholder="店頭価格">
    <button id="exact-search" type="button">同じ商品を探す</button>
  </div>
  <p class="exact-guide">容量違いを誤比較しないため、自動で決め打ちせず候補から同じ商品を選ぶ方式です。</p>
  <div class="exact-status" id="exact-status"></div>
  <div class="exact-candidates" id="exact-candidates"></div>
  <div class="exact-result" id="exact-result" aria-live="polite"></div>
</section>
<script>
(() => {{
  const API = {API!r};
  const SHIPPING_API = {SHIPPING_API!r};
  const nameEl = document.getElementById('exact-name');
  const storeEl = document.getElementById('exact-store-price');
  const searchBtn = document.getElementById('exact-search');
  const statusEl = document.getElementById('exact-status');
  const candidatesEl = document.getElementById('exact-candidates');
  const resultEl = document.getElementById('exact-result');
  let rows = [];
  let searchTerm = '';
  const yen = (n) => '¥' + Number(n || 0).toLocaleString('ja-JP');
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, c => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]));
  const wait = (ms) => new Promise(r => setTimeout(r, ms));

  async function fallbackPrice(p) {{
    const params = new URLSearchParams();
    if (p.product_code) params.set('code', p.product_code);
    if (p.name) params.set('name', p.name);
    if (p.brand) params.set('brand', p.brand);
    const response = await fetch(`${{SHIPPING_API}}?${{params.toString()}}`, {{mode:'cors'}});
    if (!response.ok) return p;
    const data = await response.json();
    if (data?.found && Number(data.shipping_included_price || 0) > 0) {{
      return {{...p,
        shipping_included_price:Number(data.shipping_included_price),
        shipping_included_url:data.shipping_included_url || p.url,
        shipping_included_shop:data.shipping_included_shop || '',
        shipping_included_image:data.shipping_included_image || ''
      }};
    }}
    return p;
  }}

  function card(p, index) {{
    const price = Number(p.shipping_included_price || 0);
    const img = p.shipping_included_image || p.image || '';
    return `<div class="exact-candidate"><div class="exact-img">${{img ? `<img src="${{esc(img)}}" alt="" loading="lazy">` : ''}}</div><div><div class="exact-brand">${{esc(p.brand || '')}}</div><div class="exact-name">${{esc(p.name || '')}}</div><div class="exact-price">${{price ? `${{yen(price)}} <small>送料込み確認済み</small>` : '<small>送料込み価格を確認できませんでした</small>'}}</div><button class="exact-choose" data-index="${{index}}" type="button" ${{price ? '' : 'disabled'}}>この商品と比較</button></div></div>`;
  }}

  function render() {{
    candidatesEl.innerHTML = rows.map(card).join('');
    const priced = rows.filter(p => Number(p.shipping_included_price || 0) > 0).length;
    statusEl.textContent = rows.length ? `候補 ${{rows.length}}件・送料込み価格確認済み ${{priced}}件` : '同じ商品候補が見つかりませんでした。商品名を少し短くして試してください。';
  }}

  async function search() {{
    const term = nameEl.value.trim();
    const storePrice = Number(storeEl.value || 0);
    resultEl.className = 'exact-result';
    resultEl.innerHTML = '';
    if (term.length < 2 || storePrice <= 0) {{
      statusEl.textContent = '商品名と店頭価格を入力してください。';
      candidatesEl.innerHTML = '';
      return;
    }}
    searchTerm = term;
    searchBtn.disabled = true;
    statusEl.textContent = '同じ商品の候補と送料込み価格を確認中…';
    candidatesEl.innerHTML = '<div class="exact-loading">楽天の商品候補を確認しています…</div>';
    try {{
      const response = await fetch(`${{API}}?q=${{encodeURIComponent(term)}}&page=1&hits=12`, {{mode:'cors'}});
      if (!response.ok) throw new Error(`HTTP ${{response.status}}`);
      const data = await response.json();
      rows = (Array.isArray(data.products) ? data.products : []).slice(0, 6);
      for (let i = 0; i < rows.length; i += 1) {{
        if (!Number(rows[i].shipping_included_price || 0)) {{
          try {{ rows[i] = await fallbackPrice(rows[i]); }} catch (_) {{}}
          if (i < rows.length - 1) await wait(1150);
        }}
      }}
      render();
      if (typeof window.gtag === 'function') window.gtag('event','same_product_compare_search',{{search_term:term,result_count:rows.length,shipping_priced_count:rows.filter(p=>Number(p.shipping_included_price||0)>0).length}});
    }} catch (err) {{
      console.error(err);
      rows = [];
      candidatesEl.innerHTML = '';
      statusEl.textContent = '楽天の価格確認に接続できませんでした。少し時間をおいて再度お試しください。';
    }} finally {{
      searchBtn.disabled = false;
    }}
  }}

  function choose(index) {{
    const p = rows[index];
    const store = Number(storeEl.value || 0);
    const rakuten = Number(p?.shipping_included_price || 0);
    if (!p || store <= 0 || rakuten <= 0) return;
    const diff = Math.abs(store - rakuten);
    let verdict;
    if (store < rakuten) verdict = `🏪 店頭で買う方が ${{yen(diff)}} 安い`;
    else if (rakuten < store) verdict = `🛒 楽天の方が ${{yen(diff)}} 安い`;
    else verdict = '＝ 店頭と楽天は同じ価格';
    const url = p.shipping_included_url || p.url || '#';
    resultEl.className = 'exact-result show';
    resultEl.innerHTML = `<div class="exact-verdict">${{verdict}}</div><p><strong>${{esc(p.name || '')}}</strong></p><p>店頭：<strong>${{yen(store)}}</strong> ／ 楽天送料込み：<strong>${{yen(rakuten)}}</strong></p><p class="exact-note">※画像・商品名・容量を見て同一商品であることを確認してください。楽天のポイント・クーポンは差額に含めていません。</p><a class="exact-rakuten" href="${{esc(url)}}" target="_blank" rel="nofollow sponsored noopener" data-exact-rakuten="1">楽天のこの商品を見る</a>`;
    resultEl.scrollIntoView({{behavior:'smooth',block:'nearest'}});
    if (typeof window.gtag === 'function') window.gtag('event','same_product_compare_select',{{search_term:searchTerm,product_id:p.product_id||'',store_price:store,rakuten_shipping_price:rakuten,difference:store-rakuten}});
  }}

  searchBtn.addEventListener('click', search);
  nameEl.addEventListener('keydown', e => {{ if (e.key === 'Enter') {{ e.preventDefault(); search(); }} }});
  candidatesEl.addEventListener('click', e => {{ const b=e.target.closest('.exact-choose'); if(b&&!b.disabled) choose(Number(b.dataset.index)); }});
  resultEl.addEventListener('click', e => {{ const a=e.target.closest('[data-exact-rakuten]'); if(a&&typeof window.gtag==='function') window.gtag('event','same_product_rakuten_click',{{search_term:searchTerm}}); }});
}})();
</script>
'''

anchor = markup.find('<section class="product-finder-home" id="product-finder-home">')
if anchor >= 0:
    end = section_end(markup, anchor)
    if end >= 0:
        markup = markup[:end] + "\n" + section + markup[end:]
    else:
        markup = markup.replace('<section class="decision-tool"', section + '\n<section class="decision-tool"', 1)
else:
    markup = markup.replace('<section class="decision-tool"', section + '\n<section class="decision-tool"', 1)

PAGE.write_text(markup, encoding="utf-8")
print("Added exact same-product store-vs-Rakuten comparison tool")
