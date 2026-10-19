"""Independent, deterministic purchase-purpose layer; never edits source offers.

Only fixed three category bands are authorized. Unknown SKU identity is not
counted as diversity. Disjoint verified quantities prove different sale packs;
identical quantities are never used as multiple purpose choices.
"""
from __future__ import annotations
import hashlib
import html
import json
import re
from pathlib import Path
from urllib.parse import urlsplit, parse_qs, unquote
from step4_purchase_audit import verify_snapshot, BANDS, hashed_id
from product_quality import filter_items, parsed_quantity
from sale_quantity import normalize
from comparison_units import comparison_unit, LABELS
from product_display import clean_display_name

VERSION = 'purchase-purpose-v1'
ROOT = '/daily-cost-jp/'
CATEGORIES = ('laundry', 'tissue', 'toilet-paper')
PURPOSES = {'small': '少量で試す・買いやすい', 'everyday': '普段使い', 'bulk': '単価重視のまとめ買い'}


def payment_tradeoffs(slots):
    """Observe totals across verified packs, without same-product/savings claims."""
    result=[]
    purposes=tuple(PURPOSES)
    for i, smaller in enumerate(purposes):
        a=slots[smaller]
        if not a:continue
        for larger in purposes[i+1:]:
            b=slots[larger]
            if (not b or a['offer']['metric']!=b['offer']['metric'] or a['unit'][0]!=b['unit'][0]
                or a['quantity']>=b['quantity'] or a['offer']['price']<=b['offer']['price']):continue
            result.append({'smaller_purpose':smaller,'larger_purpose':larger,
                'smaller_quantity':a['quantity'],'larger_quantity':b['quantity'],
                'metric':a['offer']['metric'],'comparison_unit':a['unit'][0],
                'smaller_total_yen':a['offer']['price'],'larger_total_yen':b['offer']['price'],
                'smaller_offer_ref':hashed_id(a['offer'])[0],'larger_offer_ref':hashed_id(b['offer'])[0],
                'same_product_verified':False,'automatic_substitution':False})
    return result


def destination_matches(item):
    """Shop item code must match the exact seller URL, including affiliate pc."""
    code = item.get('item_code', '')
    if not isinstance(code, str) or not re.fullmatch(r'[^:/\s]+:[^:/\s]+', code):
        return False
    try:
        url = urlsplit(item['url'])
        shop, key = code.split(':', 1)
        if url.hostname == 'hb.afl.rakuten.co.jp':
            query = parse_qs(url.query)
            target, mobile = query.get('pc', []), query.get('m', [])
            if len(target) != 1: return False
            url = urlsplit(target[0])
            if len(mobile) == 1:
                m = urlsplit(mobile[0])
                if (m.scheme in ('http','https') and m.hostname == 'm.rakuten.co.jp' and
                    not m.username and not m.password and m.port is None and
                    unquote(m.path).strip('/') == shop + '/i/' + key and
                    url.scheme == 'https' and url.hostname == 'item.rakuten.co.jp' and
                    not url.username and not url.password and url.port is None and
                    re.fullmatch(re.escape(shop) + r'/[^/]+', unquote(url.path).strip('/'))):
                    return True
        return (url.scheme == 'https' and url.hostname == 'item.rakuten.co.jp' and
                not url.username and not url.password and url.port is None and
                unquote(url.path).strip('/') == shop + '/' + key)
    except (KeyError, TypeError, ValueError):
        return False


def sale_band(cid, item, qty):
    limits = BANDS.get((cid, item['metric']))
    if not limits: return None
    small, bulk = limits
    text = normalize(item['name'])
    if cid == 'laundry':
        # Six separate bottles are not a household trial even at modest volume.
        counts = re.findall(r'x\s*(\d+)', text, re.I) + re.findall(r'(?:【\s*|\[\s*)(\d+)\s*(?:個|袋|本)(?:セット)?', text, re.I)
        if counts and max(map(int, counts)) > 2: return 'bulk'
        if re.search(r'業務用', text): return 'bulk'
    return 'small' if qty <= small else 'bulk' if qty >= bulk else 'everyday'


def specialized_household_use(cid, name):
    return (bool(re.search(r'作業着|作業服|作業衣|ユニフォーム|業務用|工業用|医療用|施設用|法人|企業.*限定|事業者.*限定', name)) or
            cid == 'tissue' and bool(re.search(r'鼻セレブ|ローション|保湿|メントール', name)))


def verified_purpose_candidates(cid, category):
    """Revalidate the separate STEP5 pool; flags/reports never authorize URLs."""
    if cid not in CATEGORIES or not isinstance(category, dict) or category.get('error'):
        return []
    ranked, rows = category.get('items'), category.get('purpose_candidates', [])
    if (not isinstance(ranked, list) or len(ranked) > 100 or any(not isinstance(r, dict) for r in ranked) or
        not isinstance(rows, list) or len(rows) > 30 or any(not isinstance(r, dict) for r in rows)):
        return []
    try:
        safe_ranked, safe_rows = filter_items(cid, ranked), filter_items(cid, rows)
    except (KeyError, TypeError, ValueError, AttributeError):
        return []
    families = {u[0] for r in safe_ranked if (u := comparison_unit(cid, r))}
    if len(families) != 1:
        return []
    family = next(iter(families))
    safe = []
    # Whole-group outliers must be removed before any per-offer checks.
    for row in safe_rows:
        qty, unit = parsed_quantity(cid, row['name']), comparison_unit(cid, row)
        if (qty and unit and unit[0] == family and destination_matches(row) and
            not specialized_household_use(cid, row['name']) and
            sale_band(cid, row, qty['quantity']) in ('small', 'everyday')):
            safe.append(row)
    return safe


def select_category(cid, category):
    empty = {p: None for p in PURPOSES}
    result = {'status': 'NO_VERIFIED_CANDIDATES', 'slots': empty, 'reasons': [], 'distinct_sku_count': None}
    if not isinstance(category, dict) or category.get('error'): return result
    rows = category.get('items')
    if not isinstance(rows, list) or len(rows) > 100 or any(not isinstance(r, dict) for r in rows): return result
    candidates = filter_items(cid, rows)
    candidates += verified_purpose_candidates(cid, category)
    extra = category.get('small_pack_offer') if cid == 'tissue' else None
    if isinstance(extra, dict):
        candidates += filter_items(cid, [extra])
    groups = {p: [] for p in PURPOSES}
    for row in candidates:
        from step4_purchase_audit import positive_number
        if any(positive_number(row.get(k)) is None for k in ('price','unit_price','confidence')): continue
        if not destination_matches(row): continue
        quantity = parsed_quantity(cid, row['name'])
        unit = comparison_unit(cid, row)
        if not quantity or not unit: continue
        band = sale_band(cid, row, quantity['quantity'])
        if not band: continue
        # Exact name+quantity is an offer specification, not a guessed brand/JAN.
        spec = hashlib.sha256(json.dumps([cid, normalize(row['name']), row['metric'], quantity['quantity']], ensure_ascii=False).encode()).hexdigest()[:24]
        groups[band].append({'offer': dict(row), 'quantity': quantity['quantity'], 'unit': list(unit), 'spec_ref': spec})
    # Choose one metric family only. No mass/volume or ply comparisons across families.
    families = sorted({r['unit'][0] for group in groups.values() for r in group})
    if len(families) > 1:
        result['reasons'].append('MULTIPLE_COMPARISON_FAMILIES_USE_CATEGORY_RANKING')
        return result
    seen = set()
    sale_packs = set()
    for purpose in PURPOSES:
        group = groups[purpose]
        group.sort(key=lambda r: ((r['unit'][1], r['offer']['price']) if purpose == 'bulk' else
                                 (r['offer']['price'], r['quantity'], r['unit'][1])) + (r['spec_ref'], r['offer']['item_code']))
        for row in group:
            pack = (row['offer']['metric'], row['quantity'])
            if row['spec_ref'] in seen or pack in sale_packs: continue
            result['slots'][purpose] = row
            seen.add(row['spec_ref']); sale_packs.add(pack)
            break
    result['status'] = 'SELECTED' if seen else 'NO_VERIFIED_CANDIDATES'
    result['reasons'] += ['NO_' + p.upper() + '_CANDIDATE' for p,r in result['slots'].items() if r is None]
    return result


def select(snapshot, now=None):
    status = verify_snapshot(snapshot, now)
    result = {'version': VERSION, 'status': status, 'catalog_updated_at': snapshot.get('updated_at') if isinstance(snapshot,dict) else None,
              'categories': {}, 'ranking_changed': False, 'sales_status': 'NOT_CONNECTED'}
    if status != 'TRUSTED_RECENT': return result
    result['categories'] = {cid: select_category(cid, snapshot['categories'].get(cid)) for cid in CATEGORIES}
    return result


def esc(x): return html.escape(str(x), quote=True)

def block(cid, result, name):
    search = ROOT + 'products/'
    parts = []
    for purpose, label in PURPOSES.items():
        r = result['slots'][purpose]
        if r is None:
            content = f'<p>確認できる候補なし</p><a href="{search}" data-conversion-source="product_search">商品名・容量から探す →</a>'
        else:
            p = r['offer']
            unit_label = LABELS.get(p['metric'], p['metric'])
            qty_label = (f'{r["quantity"]*100:g}g' if p['metric']=='100g' else f'{r["quantity"]*100:g}ml' if p['metric']=='100ml' else f'{r["quantity"]:g}' + {'box':'箱','roll':'ロール'}.get(p['metric'],''))
            normalized = f' · ¥{r["unit"][1]:,.2f}／{esc(r["unit"][0])}' if r['unit'][0] != unit_label else ''
            image = p.get('image','')
            photo = f'<img src="{esc(image)}" alt="" loading="lazy" width="96" height="96">' if isinstance(image,str) and image.startswith('https://') else ''
            content = (photo + f'<h4>{esc(clean_display_name(p["name"]))}</h4><p>確認できた総数量：{esc(qty_label)}</p>'
                       f'<p>支払総額 <strong>¥{p["price"]:,.0f}</strong>（送料込み）</p>'
                       f'<p>¥{p["unit_price"]:,.2f}／{esc(unit_label)}{normalized}</p>'
                       f'<p class="step4-reason">{esc(label)}：' + ('この数量区分の確認済み候補から同じ比較単位の単価を重視。保管場所もご確認ください。' if purpose=='bulk' else 'この数量区分の確認済み候補から支払総額を重視。用途・ブランドもご確認ください。') + '</p>'
                       f'<a class="buy-button" href="{esc(p["url"])}" target="_blank" rel="nofollow sponsored noopener" data-conversion-source="category" data-category-id="{cid}" data-id="{esc(r["spec_ref"])}" data-purchase-purpose="{purpose}" data-shipping-price="{p["price"]}">楽天でこの商品を確認する ↗</a>')
        parts.append(f'<article class="step4-purpose" data-purpose="{purpose}"><h3>{label}</h3>{content}</article>')
    return (f'<section class="step4-recommendations" data-step4-category="{cid}" aria-label="{esc(name)}の購入目的別候補"><h2>{esc(name)}：買う量から選ぶ</h2>'
            '<p>単価ランキングとは別の選び方です。数量区分は家庭での扱いやすさの目安です。</p><div class="step4-grid">' + ''.join(parts) + '</div>'
            f'<p><a href="{search}" data-conversion-source="product_search">いつもの商品を探す →</a> ブランド・商品名・容量を入力して確認できます。</p>'
            '<p class="step4-caution">価格・在庫・地域別送料は変動します。購入前に楽天で最新の条件を確認してください。</p></section>')


CSS = '''.step4-home-purpose{margin:12px 0;border:1px solid #dfcdbf;border-radius:12px;background:#fffaf6}.step4-home-purpose>summary{min-height:44px;padding:14px 16px;font-size:16px;font-weight:700;cursor:pointer}.step4-home-purpose .step4-recommendations{border:0;margin:0}.step4-recommendations{margin:24px 0;padding:20px;border:1px solid #dfcdbf;border-radius:14px;background:#fffaf6;color:#342f2c}.step4-recommendations h2{font-size:20px;margin:0 0 12px}.step4-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px}.step4-purpose{min-width:0;padding:12px;background:#fff;border-radius:10px;overflow-wrap:anywhere}.step4-purpose h3{font-size:16px;margin:0 0 10px}.step4-purpose h4{font-size:14px;line-height:1.6}.step4-purpose p{font-size:13px;line-height:1.7}.step4-purpose img{object-fit:contain;max-width:100%}.step4-recommendations a{display:inline-flex;align-items:center;min-height:44px;padding:8px 4px;max-width:100%;white-space:normal}.step4-purpose .buy-button{font-size:13px}.step4-caution{font-size:12px;color:#5f5650}.step4-recommendations a:focus-visible{outline:3px solid #22663a;outline-offset:3px}@media(max-width:650px){.step4-grid{grid-template-columns:1fr}.step4-recommendations{padding:16px}}'''


def apply(site=Path('site'), *, enabled=False):
    snapshot = json.loads((site/'data.json').read_text())
    report = select(snapshot)
    report['display_enabled'] = bool(enabled)
    # Public state contains anonymous evidence only, never raw search terms.
    public = {**report, 'categories': {cid:{**r,'slots': {p: ({k:v for k,v in row.items() if k!='offer'} | {'price_total_yen':row['offer']['price'], 'offer_ref':hashlib.sha256(row['offer']['item_code'].encode()).hexdigest()[:20]}) if row else None for p,row in r['slots'].items()}} for cid,r in report['categories'].items()}}
    (site/'purchase-recommendations.json').write_text(json.dumps(public,ensure_ascii=False,indent=2))
    if not enabled or report['status'] != 'TRUSTED_RECENT': return report
    paths = [site/'index.html'] + [site/'categories'/cid/'index.html' for cid in CATEGORIES]
    for path in paths:
        if not path.exists(): continue
        markup = path.read_text(encoding='utf-8')
        if '</main>' not in markup or '</head>' not in markup or 'data-step4-category=' in markup: continue
        cids = CATEGORIES if path == site/'index.html' else (path.parent.name,)
        blocks = []
        for cid in cids:
            c = snapshot['categories'].get(cid)
            r = report['categories'][cid]
            if not isinstance(c,dict) or c.get('error'): continue
            section_markup = block(cid, r, c.get('name',cid))
            if path == site/'index.html':
                section_markup = f'<details class="step4-home-purpose"><summary>{esc(c.get("name",cid))}：買う量から選ぶ</summary>'+section_markup+'</details>'
            blocks.append(section_markup)
        if not blocks: continue
        anchor = re.search(r'<section\b[^>]*id="purchase-tools"[^>]*>', markup)
        position = anchor.start() if anchor else markup.index('</main>')
        markup = markup[:position] + ''.join(blocks) + markup[position:]
        markup = markup.replace('</head>', '<style id="step4-purpose-style">'+CSS+'</style></head>', 1)
        path.write_text(markup,encoding='utf-8')
    return report


if __name__ == '__main__':
    import os
    apply(enabled=os.environ.get('STEP4_ENABLE_CONTENT') == 'true')
