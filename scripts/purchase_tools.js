/* Saved IDs are resolved against the current catalog; stale prices/links are never reused. */
(() => {
  const ROOT = '/daily-cost-jp/';
  const KEY = 'daily_cost_saved_products_v1';
  const selected = new Set();
  let saved = new Set();
  let mode = 'comparison';
  let catalog = [];
  const status = document.getElementById('purchase-tool-status');
  const panel = document.getElementById('purchase-tool-panel');
  if (!panel || !status) return;
  try {
    const raw = JSON.parse(localStorage.getItem(KEY) || '[]');
    saved = new Set(Array.isArray(raw) ? raw.filter(x => typeof x === 'string').slice(0, 50) : []);
  } catch (_) { status.textContent = '保存を読み込めません。このタブでは比較を使えます。'; }
  const money = n => '¥' + Number(n).toLocaleString('ja-JP', {minimumFractionDigits:2,maximumFractionDigits:2});
  function node(tag, text) { const el = document.createElement(tag); if (text) el.textContent = text; return el; }
  function persist() {
    try { localStorage.setItem(KEY, JSON.stringify([...saved])); return true; }
    catch (_) { status.textContent = '保存できませんでした。ブラウザの保存設定を確認してください。比較はこのタブ内で使えます。'; return false; }
  }
  function sync() {
    document.querySelectorAll('[data-product-tool]').forEach(b => {
      const set = b.dataset.productTool === 'save' ? saved : selected;
      const on = set.has(b.dataset.productKey);
      b.setAttribute('aria-pressed', String(on));
      b.textContent = b.dataset.productTool === 'save' ? (on ? '保存済み' : '保存する') : (on ? '比較に追加済み' : '比較する');
    });
    document.getElementById('show-saved').textContent = `保存した商品を見る（${saved.size}）`;
    document.getElementById('show-comparison').textContent = `比較を見る（${selected.size}）`;
  }
  function show() {
    panel.replaceChildren(); panel.hidden = false;
    const set = mode === 'saved' ? saved : selected;
    panel.append(node('h3', mode === 'saved' ? '保存した商品' : '選んだ商品の比較'));
    const rows = catalog.filter(p => set.has(p.key));
    if (!set.size) panel.append(node('p', '商品カードから保存・比較する商品を選んでください。'));
    if (rows.length !== set.size) panel.append(node('p', '現在の掲載候補にない保存商品があります。以前の価格・リンクでは購入を案内しません。'));
    if (mode === 'comparison' && rows.length > 1) {
      const first = rows[0];
      const same = first.unit && rows.every(p => p.category === first.category && p.unit && p.unit[0] === first.unit[0]);
      if (same) {
        rows.sort((a,b) => a.unit[1] - b.unit[1]);
        const diff = rows[rows.length-1].unit[1] - rows[0].unit[1];
        panel.append(node('p', `${first.unit[0]}あたりの安い順。単価差は最大${money(diff)}。用途・濃縮度・素材も確認してください。`));
        if (rows.some(p => p.price < rows[0].price)) panel.append(node('p','支払総額が低い候補と、単価が低い候補は異なります。購入する量も合わせて確認してください。'));
      } else panel.append(node('p', 'カテゴリ・比較単位が異なるため、安い順には並べません。同じ用途・単位の商品を選んでください。'));
    }
    const list = node('ul');
    rows.forEach(p => {
      const row = node('li');
      if (p.image && /^https:\/\//.test(p.image)) {
        const image = node('img'); image.src=p.image;image.alt=p.name;image.width=100;image.height=100;image.loading='lazy';image.className='comparison-photo';row.append(image);
      }
      row.append(node('strong', p.name));
      row.append(node('p', `${p.quantity}・支払総額 ${money(p.price)}（送料込み）`));
      row.append(node('p', p.unit ? `${money(p.unit[1])}／${p.unit[0]}` : '組数・長さ・重ね数が不明のため条件をそろえた比較対象外'));
      row.append(node('p', `取得日時：${p.updated_at.replace('T',' ').slice(0,16)}（日本時間）`));
      const link = node('a', '楽天で最新価格・送料を確認');
      link.href = p.url; link.target = '_blank'; link.rel = 'nofollow sponsored noopener';
      link.dataset.conversionSource = mode === 'saved' ? 'saved' : 'comparison';
      link.dataset.categoryId = p.category; link.dataset.id = p.key; link.dataset.rank = p.rank;
      link.dataset.productName = p.name; link.dataset.shippingPrice = p.price;
      row.append(link);
      const remove = node('button','一覧から外す'); remove.type = 'button';
      remove.addEventListener('click', () => { set.delete(p.key); if(mode==='saved')persist();sync();show(); });
      row.append(remove); list.append(row);
    }); panel.append(list);
    const clear = node('button','この一覧を空にする');clear.type = 'button';
    clear.addEventListener('click',()=>{set.clear();if(mode==='saved')persist();sync();show();});panel.append(clear);
    const close=node('button','比較・保存の一覧を閉じる');close.type='button';close.addEventListener('click',()=>{panel.hidden=true;});panel.append(close);
  }
  document.getElementById('show-saved').addEventListener('click',()=>{mode='saved';show();panel.scrollIntoView?.({behavior:'auto',block:'start'});});
  document.getElementById('show-comparison').addEventListener('click',()=>{mode='comparison';show();panel.scrollIntoView?.({behavior:'auto',block:'start'});});
  fetch(ROOT+'assets/comparison-catalog.json').then(r=>{if(!r.ok)throw new Error('catalog');return r.json();}).then(data=>{
    catalog = data;
    document.querySelectorAll('.product-card, .deal-card').forEach(card=>{
      const link = card.querySelector('a[href*="hb.afl.rakuten.co.jp"]');
      const p = catalog.find(p=>p.url===link?.href);if(!p)return;
      link.dataset.id=p.key;link.dataset.categoryId=p.category;link.dataset.rank=p.rank;link.dataset.shippingPrice=p.price;
      const body=card.querySelector('.product-body, .deal-body')||card;
      const history=node('p');history.className='history-fact';
      history.textContent=p.history ? `${p.history.days}日分の観測：前回 ${money(p.history.previous)}・観測期間の最安 ${money(p.history.minimum)}（支払総額）。` : '同じ商品の価格履歴は蓄積中です。買い時は断定しません。';
      body.append(history);
      const tools=node('div');tools.className='product-tools';
      ['save','compare'].forEach(kind=>{
        const button=node('button');button.type='button';button.dataset.productTool=kind;button.dataset.productKey=p.key;
        button.addEventListener('click',()=>{
          const set=kind==='save'?saved:selected;
          if(set.has(p.key))set.delete(p.key);
          else {if(set.size>=(kind==='save'?50:4)){status.textContent=kind==='save'?'保存は50商品までです。':'一度に比較できるのは4商品までです。';return;}set.add(p.key);}
          const ok=kind==='save'?persist():true;sync();if(ok)status.textContent=kind==='save'?'保存一覧を更新しました。':'比較候補を更新しました。「比較を見る」で確認できます。';
          if(!panel.hidden)show();
        });tools.append(button);
      });body.append(tools);
    });sync();
  }).catch(()=>{status.textContent='比較用データを読み込めませんでした。表示中の価格を確認し、ページを再読み込みしてください。';});
})();
