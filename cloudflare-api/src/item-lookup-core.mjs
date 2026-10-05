export function parseRakutenItemUrl(value){
  let url;
  try{url=new URL(String(value||""));}catch{return null;}
  if(url.protocol!=="https:"||url.hostname!=="item.rakuten.co.jp")return null;
  const parts=url.pathname.split("/").filter(Boolean);
  if(parts.length!==2)return null;
  const [shopCode,itemId]=parts.map(part=>decodeURIComponent(part).trim());
  if(!/^[A-Za-z0-9_-]+$/.test(shopCode)||!/^[A-Za-z0-9_-]+$/.test(itemId))return null;
  return {
    shopCode,
    itemId,
    itemCode:`${shopCode}:${itemId}`,
    canonicalUrl:`https://item.rakuten.co.jp/${shopCode}/${itemId}/`
  };
}

export function canonicalRakutenItemUrl(value){
  return parseRakutenItemUrl(value)?.canonicalUrl||"";
}

export function affiliateTargetsItem(affiliateUrl,itemUrl){
  let url;
  try{url=new URL(String(affiliateUrl||""));}catch{return false;}
  if(url.protocol!=="https:"||url.hostname!=="hb.afl.rakuten.co.jp")return false;
  const pc=url.searchParams.get("pc");
  if(!pc)return false;
  return canonicalRakutenItemUrl(pc)===canonicalRakutenItemUrl(itemUrl);
}
