// Validate the seller's type and pack before comparing with a single product.
// The Worker response includes shipping_match_name; selectable variants can
// otherwise assign a listing's minimum price to a different size or pack.
window.dailyCostVerifiedOffer = function(product) {
  const p = { ...product };
  const title = String(p.shipping_match_name || '').normalize('NFKC').toLowerCase().replace(/[×✕*]/g, 'x').replace(/,/g, '');
  const wanted = String(p.name || '').normalize('NFKC').toLowerCase();
  // Capacity/brand matches alone can confuse standard, drum-only and indoor
  // drying detergents. Recheck both bulk results and later fallback responses.
  const refill = /詰[め]?替[え]?|つめかえ|つめ替え|リフィル|レフィル/;
  const mixedForm = refill.test(title) && /本体/.test(title);
  const differentForm = (refill.test(wanted) && /本体/.test(title)) ||
    (/本体/.test(wanted) && refill.test(title));
  const differentType = Boolean(wanted && title) && (
    [/ドラム/, /部屋干し/].some(type => type.test(wanted) !== type.test(title)) ||
    mixedForm || differentForm);
  const selectable = /(?:種類|タイプ|サイズ|容量|個数)を選べる|選べる.{0,12}(?:\d|個数|容量|サイズ|種類|タイプ)|\d+\s*(?:個|袋|本|箱|パック)?\s*[~〜～/／]\s*\d+\s*(?:個|袋|本|箱|パック)|\d+種から/.test(title);
  const capacities = [...title.matchAll(/(\d+(?:\.\d+)?)\s*(kg|g|ml|l)/g)].map(m => {
    const scale = m[2] === 'kg' || m[2] === 'l' ? 1000 : 1;
    return `${m[2] === 'kg' || m[2] === 'g' ? 'g' : 'ml'}:${Number(m[1]) * scale}`;
  });
  const varyingPacks = ['個','袋','本','箱','パック'].some(unit =>
    new Set([...title.matchAll(new RegExp('(\\d+)\\s*' + unit, 'g'))].map(m => Number(m[1]))).size > 1);
  // Multiple capacities may also mean a mixed bundle. Do not infer its price.
  // Clear stale rejection flags if a subsequent lookup finds a matching offer.
  p.offer_type_mismatch = differentType;
  p.offer_needs_selection = Boolean(selectable || new Set(capacities).size > 1 || (capacities.length && varyingPacks));
  if (p.offer_type_mismatch || p.offer_needs_selection) {
    p.shipping_included_price = null;
    p.shipping_included_url = '';
    p.shipping_included_shop = '';
    p.shipping_included_image = '';
    p.sale_quantity_label = '';
  }
  return p;
};
