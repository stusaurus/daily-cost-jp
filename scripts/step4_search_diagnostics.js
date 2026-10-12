/* Aggregate-only search evidence. No query, product title, URL, ID or token. */
(function(root){
'use strict';
const REASONS=['PRICED_SAFE','QUANTITY_PARSE_FAILED','SHIPPING_UNKNOWN','PRODUCT_MISMATCH','DANGEROUS_EXCLUDED','UNRESOLVED','PENDING','LOOKUP_API_FAILURE','LOOKUP_TIME_LIMIT','LOOKUP_UNVERIFIED','LOOKUP_NOT_ATTEMPTED'];
function reason(p){
 if(!p||typeof p!=='object')return 'DANGEROUS_EXCLUDED';
 if(p.offer_type_mismatch||p.match_status==='mismatch')return 'PRODUCT_MISMATCH';
 if(p.offer_needs_selection||p.quantity_parse_failed===true||p.quantity_status==='unverified')return 'QUANTITY_PARSE_FAILED';
 if(p.excluded_reason||p.offer_rejected===true)return 'DANGEROUS_EXCLUDED';
 const price=Number(p.shipping_included_price);
 if(Number.isFinite(price)&&price>0){
  try{const u=new URL(p.shipping_included_url||'');if(u.protocol!=='https:'||u.username||u.password||u.port||!u.hostname.endsWith('.rakuten.co.jp'))return 'DANGEROUS_EXCLUDED';}
  catch(_){return 'DANGEROUS_EXCLUDED';}
  return 'PRICED_SAFE';
 }
 if(p.shipping_lookup_pending)return 'PENDING';
 if(p.shipping_lookup_status==='API_FAILURE')return 'LOOKUP_API_FAILURE';
 if(p.shipping_lookup_status==='TIME_LIMIT')return 'LOOKUP_TIME_LIMIT';
 if(p.shipping_lookup_status==='UNVERIFIED')return 'LOOKUP_UNVERIFIED';
 if(p.shipping_lookup_status==='NOT_ATTEMPTED')return 'LOOKUP_NOT_ATTEMPTED';
 if(p.shipping_status==='unknown'||p.postage==='送料別'||p.postage==='送料は商品ページで確認')return 'SHIPPING_UNKNOWN';
 // Missing price alone does not distinguish API, matching, quantity or shipping.
 return 'UNRESOLVED';
}
function explanation(summary){
 if(summary.status==='API_FETCH_FAILURE')return '商品取得に失敗しました。商品がないという意味ではありません。時間をおいて再検索してください。';
 if(summary.status==='API_RESPONSE_ZERO')return '一致する候補を取得できませんでした。商品名・容量・本体／詰め替えを確かめて再検索してください。';
 const c=summary.counts||{};
 const parts=[];
 if(c.PRODUCT_MISMATCH)parts.push(`用途・タイプの不一致 ${c.PRODUCT_MISMATCH}件`);
 if(c.QUANTITY_PARSE_FAILED)parts.push(`数量・選択条件の未確認 ${c.QUANTITY_PARSE_FAILED}件`);
 if(c.SHIPPING_UNKNOWN)parts.push(`送料不明 ${c.SHIPPING_UNKNOWN}件`);
 if(c.DANGEROUS_EXCLUDED)parts.push(`安全確認で除外 ${c.DANGEROUS_EXCLUDED}件`);
 if(c.LOOKUP_API_FAILURE)parts.push(`送料確認APIの失敗 ${c.LOOKUP_API_FAILURE}件`);
 if(c.LOOKUP_TIME_LIMIT)parts.push(`追加確認が時間内に完了しなかった候補 ${c.LOOKUP_TIME_LIMIT}件`);
 if(c.LOOKUP_UNVERIFIED)parts.push(`API応答後も同一出品を確認できない候補 ${c.LOOKUP_UNVERIFIED}件`);
 if(c.LOOKUP_NOT_ATTEMPTED)parts.push(`追加確認の対象上限により未確認 ${c.LOOKUP_NOT_ATTEMPTED}件`);
 if(c.UNRESOLVED)parts.push(`詳細な理由が未取得 ${c.UNRESOLVED}件`);
 const lead=summary.status==='LOOKUPS_PENDING'?`送料・同一商品を追加確認中（残り${summary.pending_count}件）です。`:
 summary.safe_priced_count===0?`候補は${summary.fetched_count}件取得しましたが、送料込み価格を確認できる候補は0件です。`:
 '送料込み価格を確認できた候補があります。購入前に楽天で最新条件をご確認ください。';
 return lead+(parts.length?' '+parts.join('、')+'。':'')+(summary.safe_priced_count===0?' 未確認の価格は補完していません。':'');
}
function summarize(rows,fetchStatus='OK'){
 const counts=Object.fromEntries(REASONS.map(k=>[k,0]));
 if(!Array.isArray(rows)||rows.length>3000||!['OK','API_FAILURE'].includes(fetchStatus))fetchStatus='API_FAILURE';
 if(fetchStatus==='API_FAILURE')return {status:'API_FETCH_FAILURE',fetched_count:null,safe_priced_count:null,pending_count:null,counts:null};
 rows.forEach(p=>counts[reason(p)]++);
 return {status:rows.length===0?'API_RESPONSE_ZERO':counts.PENDING?'LOOKUPS_PENDING':counts.PRICED_SAFE===0?'NO_SAFE_PRICED_CANDIDATES':'SAFE_PRICED_AVAILABLE',
 fetched_count:rows.length,safe_priced_count:counts.PRICED_SAFE,pending_count:counts.PENDING,counts};
}
function eventPayload(summary,phase){
 const result={diagnostic_status:summary.status,diagnostic_phase:phase==='final'?'final':'initial'};
 for(const key of ['fetched_count','safe_priced_count','pending_count'])if(Number.isInteger(summary[key])&&summary[key]>=0)result[key]=summary[key];
 if(summary.counts)for(const k of REASONS)result['reason_'+k.toLowerCase()]=summary.counts[k];
 return result;
}
const api={reason,summarize,eventPayload,explanation};
if(typeof module==='object'&&module.exports)module.exports=api;
if(root)root.dailyCostSearchDiagnostics=api;
})(typeof window==='object'?window:null);
