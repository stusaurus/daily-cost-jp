/* Aggregate-only search evidence. No query, product title, URL, ID or token. */
(function(root){
'use strict';
const REASONS=['PRICED_SAFE','QUANTITY_PARSE_FAILED','SHIPPING_UNKNOWN','PRODUCT_MISMATCH','DANGEROUS_EXCLUDED','UNRESOLVED','PENDING'];
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
 if(p.shipping_status==='unknown'||p.postage==='送料別'||p.postage==='送料は商品ページで確認')return 'SHIPPING_UNKNOWN';
 // Missing price alone does not distinguish API, matching, quantity or shipping.
 return 'UNRESOLVED';
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
const api={reason,summarize,eventPayload};
if(typeof module==='object'&&module.exports)module.exports=api;
if(root)root.dailyCostSearchDiagnostics=api;
})(typeof window==='object'?window:null);
