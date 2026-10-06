const PRODUCT_API_URL = "https://openapi.rakuten.co.jp/ichibaproduct/api/Product/Search/20250801";
const ITEM_API_URL = "https://openapi.rakuten.co.jp/ichibams/api/IchibaItem/Search/20260701";
const ALLOWED_ORIGIN = "https://stusaurus.github.io";
const SITE_URL = "https://stusaurus.github.io/daily-cost-jp/";

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function safeInt(value, fallback = 0) {
  const n = Number(value);
  return Number.isFinite(n) ? Math.trunc(n) : fallback;
}

function safeFloat(value, fallback = 0) {
  const n = Number(value);
  return Number.isFinite(n) ? n : fallback;
}

function normalize(value) {
  return String(value || "")
    .normalize("NFKC")
    .toLowerCase()
    .replace(/[\s\u3000]+/g, " ")
    .trim();
}

function compact(value) {
  return normalize(value)
    .replace(/[\s\u3000\-_/・.,!！?？()（）［］\[\]【】]/g, "")
    .replace(/巻/g, "ロール");
}

// Realtime results have no unit-price field to cross-check.  Therefore expose
// a label only for one explicit, self-contained quantity expression from the
// matched seller listing; bare model/year numbers can never match.
function saleQuantityLabel(value) {
  const text = normalize(value).replace(/[×✕*]/g, "x").replace(/,/g, "");
  if (/(種類|タイプ|サイズ|容量|個数)を選べる/.test(text)) return "";
  const measure = [...text.matchAll(/(^|[^a-z0-9.])(\d+(?:\.\d+)?)\s*(kg|g|ml|l)(?:\s*x\s*(\d+)\s*(ロール|巻|個|本|箱|パック|袋|枚|セット))?/gi)];
  if (measure.length === 1) {
    const m = measure[0];
    const unit = m[3].toLowerCase() === "l" ? "L" : m[3].toLowerCase();
    return `${Number(m[2])}${unit}${m[4] ? `×${Number(m[4])}${m[5] === "巻" ? "ロール" : m[5]}` : ""}`;
  }
  const compound = [...text.matchAll(/(^|[^a-z0-9.])(\d+)\s*(ロール|巻|個|本|箱|パック|袋|枚|組|セット)\s*x\s*(\d+)\s*(ロール|巻|個|本|箱|パック|袋|枚|セット)/gi)];
  if (compound.length === 1) {
    const m = compound[0];
    return `${Number(m[2])}${m[3] === "巻" ? "ロール" : m[3]}×${Number(m[4])}${m[5] === "巻" ? "ロール" : m[5]}`;
  }
  const single = [...text.matchAll(/(^|[^a-z0-9.])(\d+)\s*(ロール|巻|個|本|箱|パック|袋|枚)(?:入り)?/gi)];
  if (single.length !== 1) return "";
  return `${Number(single[0][2])}${single[0][3] === "巻" ? "ロール" : single[0][3]}入り`;
}

function firstImageUrl(value) {
  if (!Array.isArray(value) || !value.length) return "";
  const first = value[0];
  const url = typeof first === "string"
    ? first
    : first && typeof first === "object"
      ? first.imageUrl || first.url || ""
      : "";
  return String(url || "").replace("http://", "https://");
}

const GENERIC_WORDS = new Set([
  "楽天", "公式", "正規品", "送料無料", "送料込", "送料込み", "セール", "sale",
  "トイレットペーパー", "ティッシュ", "ティッシュペーパー", "洗剤", "シャンプー",
  "コンディショナー", "ボディソープ", "ハンドソープ", "マウスウォッシュ",
  "セット", "まとめ買い", "詰め替え", "詰替", "本体", "無香料", "ダブル", "シングル",
  "大容量", "業務用", "ケース", "パック"
]);

function wordTokens(name, brand) {
  const brandKey = compact(brand);
  return normalize(name)
    .replace(/[()（）\[\]【】/／・,，:：;；!！?？+＋×✕]/g, " ")
    .split(/\s+/)
    .map((token) => token.trim())
    .filter(Boolean)
    .filter((token) => token.length >= 2)
    .filter((token) => !/^\d+(?:\.\d+)?(?:ml|l|g|kg|m|cm|mm|枚|個|本|箱|袋|ロール|巻|パック)?$/i.test(token))
    .filter((token) => !GENERIC_WORDS.has(token))
    .filter((token) => compact(token) !== brandKey);
}

function specTokens(name) {
  const text = normalize(name).replace(/[＊*×✕]/g, "x");
  const found = text.match(/\d+(?:\.\d+)?\s*(?:ml|l|g|kg|m|cm|mm|枚|個|本|箱|袋|ロール|巻|パック)|\d+\s*in\s*1/gi) || [];
  return Array.from(new Set(found.map((token) => compact(token))));
}

function normalizeProduct(raw) {
  const productId = String(raw.productId || "").trim();
  const name = String(raw.productName || "").trim();
  if (!productId || !name) return null;
  return {
    product_id: productId,
    product_code: String(raw.productCode || ""),
    name,
    product_no: String(raw.productNo || ""),
    brand: String(raw.brandName || ""),
    genre: String(raw.genreName || ""),
    seller_count: safeInt(raw.salesItemCount),
    review_count: safeInt(raw.reviewCount),
    review_average: safeFloat(raw.reviewAverage),
    image: String(raw.mediumImageUrl || "").replace("http://", "https://"),
    url: String(raw.affiliateUrl || raw.productUrlPC || ""),
  };
}

function normalizeItem(raw) {
  const item = raw && typeof raw === "object" && raw.Item && typeof raw.Item === "object"
    ? raw.Item
    : raw && typeof raw === "object" && raw.item && typeof raw.item === "object"
      ? raw.item
      : raw;
  if (!item || typeof item !== "object") return null;
  const price = safeInt(item.itemPrice);
  if (price <= 0) return null;
  return {
    name: String(item.itemName || ""),
    price,
    shop: String(item.shopName || ""),
    url: String(item.affiliateUrl || item.itemUrl || ""),
    image: firstImageUrl(item.mediumImageUrls),
    postage_flag: safeInt(item.postageFlag, -1),
    sale_quantity_label: saleQuantityLabel(item.itemName),
  };
}

function canonicalRakutenItemUrl(value) {
  try {
    const u = new URL(String(value || ""));
    if (u.protocol !== "https:" || u.hostname !== "item.rakuten.co.jp") return "";
    const path = u.pathname.replace(/\/+/g, "/").replace(/\/+$/, "") + "/";
    return "https://item.rakuten.co.jp" + path;
  } catch {
    return "";
  }
}

function rakutenItemLocator(value) {
  const canonical = canonicalRakutenItemUrl(value);
  if (!canonical) return null;
  const u = new URL(canonical);
  const parts = u.pathname.split("/").filter(Boolean);
  if (parts.length < 2) return null;
  return { canonical, shopCode: parts[0], slug: parts.slice(1).join("/") };
}

function extractJsonObject(text, marker) {
  const markerIndex = text.indexOf(marker);
  if (markerIndex < 0) return null;
  const start = text.indexOf("{", markerIndex + marker.length);
  if (start < 0) return null;
  let depth = 0;
  let inString = false;
  let escaped = false;
  for (let i = start; i < text.length; i += 1) {
    const ch = text[i];
    if (inString) {
      if (escaped) escaped = false;
      else if (ch === "\\") escaped = true;
      else if (ch === '"') inString = false;
      continue;
    }
    if (ch === '"') { inString = true; continue; }
    if (ch === "{") depth += 1;
    else if (ch === "}") {
      depth -= 1;
      if (depth === 0) {
        try { return JSON.parse(text.slice(start, i + 1)); } catch { return null; }
      }
    }
  }
  return null;
}

function decodeHtmlText(value) {
  return String(value || "")
    .replace(/&amp;/gi, "&")
    .replace(/&quot;/gi, '"')
    .replace(/&#39;|&apos;/gi, "'")
    .replace(/&lt;/gi, "<")
    .replace(/&gt;/gi, ">")
    .replace(/&#(\d+);/g, (_, code) => String.fromCodePoint(Number(code)))
    .replace(/&#x([0-9a-f]+);/gi, (_, code) => String.fromCodePoint(parseInt(code, 16)))
    .replace(/\s+/g, " ")
    .trim();
}

function extractMetaContent(text, key) {
  const patterns = [
    new RegExp("<meta[^>]+(?:property|name)=[\\\"']" + key + "[\\\"'][^>]+content=[\\\"']([^\\\"']+)[\\\"'][^>]*>", "i"),
    new RegExp("<meta[^>]+content=[\\\"']([^\\\"']+)[\\\"'][^>]+(?:property|name)=[\\\"']" + key + "[\\\"'][^>]*>", "i"),
  ];
  for (const pattern of patterns) {
    const match = text.match(pattern);
    if (match?.[1]) return decodeHtmlText(match[1]);
  }
  return "";
}

function extractHtmlTitle(text) {
  const metaTitle = extractMetaContent(text, "og:title") || extractMetaContent(text, "twitter:title");
  if (metaTitle) return metaTitle;
  const match = text.match(/<title[^>]*>([\s\S]*?)<\/title>/i);
  return match?.[1] ? decodeHtmlText(match[1].replace(/<[^>]+>/g, " ")) : "";
}

function exactPageSearchQueries(pageInfo, suppliedQuery, locator) {
  const out = [];
  const add = (value) => {
    const clean = String(value || "").replace(/\s+/g, " ").trim();
    if (clean.length >= 2 && !out.includes(clean)) out.push(clean.slice(0, 110));
  };
  add(suppliedQuery);
  add(pageInfo?.title);
  if (pageInfo?.title) {
    add(pageInfo.title
      .replace(/【[^】]{0,40}】/g, " ")
      .replace(/＼[^＼]{0,50}＼/g, " ")
      .replace(/楽天市場/gi, " ")
      .replace(/[｜|].*$/, " "));
  }
  add(locator?.slug?.replace(/[-_/]+/g, " "));
  return out;
}

async function fetchExactRakutenPageInfo(itemUrl) {
  const canonical = canonicalRakutenItemUrl(itemUrl);
  if (!canonical) return null;
  const response = await fetch(canonical, {
    redirect: "follow",
    headers: { "User-Agent": "daily-cost-jp-cloudflare-item-lookup/1.1", Accept: "text/html,application/xhtml+xml" },
  });
  if (!response.ok) return null;
  const text = await response.text();
  const info = extractJsonObject(text, '"itemInfoSku":');
  if (!info || !Number.isInteger(info.itemId)) return null;
  const purchase = info.purchaseInfo?.purchaseBySellType || {};
  return {
    itemId: info.itemId,
    unavailable: Boolean(purchase.purchaseCondition && purchase.purchaseCondition !== "enabled"),
    title: extractHtmlTitle(text),
  };
}

function unwrapItem(raw) {
  return raw && typeof raw === "object" && raw.Item && typeof raw.Item === "object"
    ? raw.Item
    : raw && typeof raw === "object" && raw.item && typeof raw.item === "object"
      ? raw.item
      : raw;
}

function normalizeExactItem(raw) {
  const item = unwrapItem(raw);
  if (!item || typeof item !== "object") return null;
  const price = safeInt(item.itemPrice);
  const itemUrl = canonicalRakutenItemUrl(item.itemUrl);
  const affiliateUrl = String(item.affiliateUrl || "");
  if (price <= 0 || !itemUrl || !affiliateUrl.startsWith("https://hb.afl.rakuten.co.jp/")) return null;
  return {
    name: String(item.itemName || ""), price, item_url: itemUrl, affiliate_url: affiliateUrl,
    image: firstImageUrl(item.mediumImageUrls), shop_code: String(item.shopCode || ""),
    shop_name: String(item.shopName || ""), item_code: String(item.itemCode || ""),
    availability: safeInt(item.availability, 1),
  };
}

async function fetchItemByCode(itemCode, env) {
  const params = new URLSearchParams({
    applicationId: env.RAKUTEN_APPLICATION_ID, itemCode, hits: "1", format: "json", formatVersion: "2", availability: "1",
    elements: "itemName,itemCode,itemPrice,itemUrl,affiliateUrl,shopName,shopCode,availability,mediumImageUrls",
  });
  if (env.RAKUTEN_AFFILIATE_ID) params.set("affiliateId", env.RAKUTEN_AFFILIATE_ID);
  const response = await fetch(ITEM_API_URL + "?" + params.toString(), {
    headers: { accessKey: env.RAKUTEN_ACCESS_KEY, Origin: ALLOWED_ORIGIN, Referer: SITE_URL, "User-Agent": "daily-cost-jp-cloudflare-item-lookup/1.0" },
  });
  if (!response.ok) throw new Error("item_api_" + response.status);
  const payload = await response.json();
  const source = Array.isArray(payload.Items) ? payload.Items : Array.isArray(payload.items) ? payload.items : [];
  return source.map(normalizeExactItem).filter(Boolean);
}

async function fetchShopItems(q, shopCode, env) {
  const params = new URLSearchParams({
    applicationId: env.RAKUTEN_APPLICATION_ID, shopCode, keyword: q, hits: "30", format: "json", formatVersion: "2", availability: "1",
    elements: "itemName,itemCode,itemPrice,itemUrl,affiliateUrl,shopName,shopCode,availability,mediumImageUrls",
  });
  if (env.RAKUTEN_AFFILIATE_ID) params.set("affiliateId", env.RAKUTEN_AFFILIATE_ID);
  const response = await fetch(ITEM_API_URL + "?" + params.toString(), {
    headers: { accessKey: env.RAKUTEN_ACCESS_KEY, Origin: ALLOWED_ORIGIN, Referer: SITE_URL, "User-Agent": "daily-cost-jp-cloudflare-item-lookup/1.0" },
  });
  if (!response.ok) throw new Error("item_api_" + response.status);
  const payload = await response.json();
  const source = Array.isArray(payload.Items) ? payload.Items : Array.isArray(payload.items) ? payload.items : [];
  return source.map(normalizeExactItem).filter(Boolean);
}

async function exactItemLookup(itemUrl, q, itemCode, env) {
  const locator = rakutenItemLocator(itemUrl);
  if (!locator) return null;

  const explicitCode = String(itemCode || "").trim();
  if (explicitCode) {
    const separator = explicitCode.indexOf(":");
    const explicitShop = separator > 0 ? explicitCode.slice(0, separator) : "";
    if (explicitShop !== locator.shopCode) {
      return { found: false, reason: "item_code_shop_mismatch" };
    }
    try {
      const byExplicitCode = await fetchItemByCode(explicitCode, env);
      const exactByExplicitCode = byExplicitCode.find((item) => item.item_url === locator.canonical);
      if (exactByExplicitCode) {
        return { found: true, lookup_method: "item_url_explicit_item_code", ...exactByExplicitCode };
      }
    } catch (error) {
      console.error("explicit itemCode lookup failed; continuing", error);
    }
  }

  let pageInfo = null;
  try {
    pageInfo = await fetchExactRakutenPageInfo(locator.canonical);
  } catch (error) {
    // The exact product page can be slow or blocked from some runtimes. Do not let
    // that prevent the Rakuten API's shop-scoped exact URL search from running.
    console.error("exact Rakuten page lookup failed; continuing with shop search", error);
  }
  if (pageInfo?.unavailable) return { found: false, reason: "unavailable" };
  if (pageInfo?.itemId) {
    try {
      const byCode = await fetchItemByCode(locator.shopCode + ":" + pageInfo.itemId, env);
      const exact = byCode.find((item) => item.item_url === locator.canonical);
      if (exact) return { found: true, lookup_method: "item_url_item_code", ...exact };
    } catch (error) {
      console.error("page-derived itemCode lookup failed; continuing", error);
    }
  }

  const queries = exactPageSearchQueries(pageInfo, q, locator);
  for (const query of queries) {
    try {
      const items = await fetchShopItems(query, locator.shopCode, env);
      const exact = items.find((item) => item.item_url === locator.canonical);
      if (exact) {
        const method = pageInfo?.title && query !== String(q || "").trim()
          ? "item_url_page_title_search"
          : "item_url_shop_search";
        return { found: true, lookup_method: method, ...exact };
      }
    } catch (error) {
      console.error("shop-scoped item lookup failed; continuing", error);
    }
  }
  return { found: false, reason: "exact_item_not_found" };
}
function relevanceScore(product, query) {
  const q = compact(query);
  const name = compact(product.name);
  const brand = compact(product.brand);
  const code = compact(product.product_code);
  let score = 0;
  if (code && code === q) score += 10000;
  if (name === q) score += 2200;
  if (name.startsWith(q)) score += 1400;
  if (brand === q) score += 1200;
  if (name.includes(q)) score += 800;
  if (brand.includes(q)) score += 500;
  score += Math.min(150, Math.log10(product.review_count + 1) * 35);
  score += Math.min(80, Math.log10(product.seller_count + 1) * 20);
  return score;
}

function safeMatch(itemName, product) {
  const itemKey = compact(itemName);
  const productKey = compact(product.name);
  const brandKey = compact(product.brand);
  const words = wordTokens(product.name, product.brand).slice(0, 7);
  const specs = specTokens(product.name);

  const exactName = Boolean(productKey && itemKey.includes(productKey));
  const brandMatch = Boolean(brandKey && brandKey.length >= 2 && itemKey.includes(brandKey));
  let wordMatches = 0;
  for (const word of words) {
    if (itemKey.includes(compact(word))) wordMatches += 1;
  }
  let specMatches = 0;
  for (const spec of specs) {
    if (itemKey.includes(spec)) specMatches += 1;
  }

  const allSpecsMatch = specs.length === 0 || specMatches === specs.length;
  const enoughWords = words.length === 0 ? false : wordMatches >= Math.min(2, words.length);
  const identityOk = exactName || brandMatch || enoughWords;

  let score = 0;
  if (exactName) score += 70;
  if (brandMatch) score += 24;
  score += wordMatches * 10;
  score += specMatches * 15;

  // Safety-first: never accept a candidate that disagrees with size/count specs,
  // and never accept a candidate based on price/JAN search alone.
  const accepted = allSpecsMatch && identityOk && score >= 20;
  return { accepted, score, exactName, brandMatch, wordMatches, specMatches };
}

function chooseSafeItem(items, product) {
  const ranked = items
    .map((item) => ({ item, ...safeMatch(item.name, product) }))
    .filter((x) => x.accepted)
    .sort((a, b) => (b.score - a.score) || (a.item.price - b.item.price));
  if (!ranked.length) return null;
  const bestScore = ranked[0].score;
  return ranked
    .filter((x) => x.score >= bestScore - 4)
    .sort((a, b) => a.item.price - b.item.price)[0];
}

function attachShipping(products, items) {
  return products.map((product) => {
    const best = chooseSafeItem(items, product);
    if (!best) {
      return {
        ...product,
        shipping_included_price: null,
        shipping_included_url: "",
        shipping_included_shop: "",
        shipping_included_image: "",
      };
    }
    return {
      ...product,
      shipping_included_price: best.item.price,
      shipping_included_url: best.item.url,
      shipping_included_shop: best.item.shop,
      shipping_included_image: best.item.image,
      shipping_match_score: best.score,
      shipping_match_name: best.item.name,
      sale_quantity_label: best.item.sale_quantity_label,
    };
  });
}

async function fetchProductCandidates(q, page, hits, env) {
  const params = new URLSearchParams({
    applicationId: env.RAKUTEN_APPLICATION_ID,
    keyword: q,
    hits: String(hits),
    page: String(page),
    format: "json",
    formatVersion: "2",
    elements: [
      "productId", "productCode", "productName", "productNo", "brandName",
      "productUrlPC", "affiliateUrl", "mediumImageUrl", "salesItemCount",
      "reviewCount", "reviewAverage", "genreName"
    ].join(","),
  });
  if (env.RAKUTEN_AFFILIATE_ID) params.set("affiliateId", env.RAKUTEN_AFFILIATE_ID);

  const response = await fetch(`${PRODUCT_API_URL}?${params.toString()}`, {
    headers: {
      accessKey: env.RAKUTEN_ACCESS_KEY,
      Origin: ALLOWED_ORIGIN,
      Referer: SITE_URL,
      "User-Agent": "daily-cost-jp-cloudflare/1.1",
    },
  });
  if (!response.ok) throw new Error(`product_api_${response.status}`);
  const payload = await response.json();
  const source = Array.isArray(payload.Products)
    ? payload.Products
    : Array.isArray(payload.items)
      ? payload.items
      : [];
  const products = source
    .map((row) => row && typeof row === "object" && row.Product ? row.Product : row)
    .filter((row) => row && typeof row === "object")
    .map(normalizeProduct)
    .filter(Boolean)
    .sort((a, b) => relevanceScore(b, q) - relevanceScore(a, q));
  return { products, pageCount: safeInt(payload.pageCount), totalCount: safeInt(payload.count) };
}

async function fetchIncludedItems(q, env, page = 1) {
  const params = new URLSearchParams({
    applicationId: env.RAKUTEN_APPLICATION_ID,
    keyword: q,
    hits: "30",
    page: String(page),
    format: "json",
    formatVersion: "2",
    availability: "1",
    field: "0",
    sort: "+itemPrice",
    postageFlag: "1",
    elements: "itemName,itemPrice,itemUrl,affiliateUrl,shopName,postageFlag,mediumImageUrls",
  });
  if (env.RAKUTEN_AFFILIATE_ID) params.set("affiliateId", env.RAKUTEN_AFFILIATE_ID);

  const response = await fetch(`${ITEM_API_URL}?${params.toString()}`, {
    headers: {
      accessKey: env.RAKUTEN_ACCESS_KEY,
      Origin: ALLOWED_ORIGIN,
      Referer: SITE_URL,
      "User-Agent": "daily-cost-jp-cloudflare-shipping/1.2",
    },
  });
  if (!response.ok) throw new Error(`item_api_${response.status}`);
  const payload = await response.json();
  const source = Array.isArray(payload.Items)
    ? payload.Items
    : Array.isArray(payload.items)
      ? payload.items
      : [];
  return source
    .map(normalizeItem)
    .filter(Boolean)
    .filter((item) => item.postage_flag === 0);
}

async function fetchIncludedItemPages(q, env, maxPages = 3) {
  const items = [];
  const seen = new Set();
  for (let page = 1; page <= maxPages; page += 1) {
    if (page > 1) await sleep(1100);
    const batch = await fetchIncludedItems(q, env, page);
    for (const item of batch) {
      const key = `${item.url}|${item.price}|${item.name}`;
      if (seen.has(key)) continue;
      seen.add(key);
      items.push(item);
    }
    if (batch.length < 30) break;
  }
  return items;
}

function fallbackKeyword(name, brand) {
  const parts = [];
  if (brand) parts.push(String(brand));
  parts.push(...wordTokens(name, brand).slice(0, 4));
  parts.push(...specTokens(name).slice(0, 3));
  const seen = new Set();
  return parts
    .map((part) => String(part || "").trim())
    .filter(Boolean)
    .filter((part) => {
      const key = compact(part);
      if (!key || seen.has(key)) return false;
      seen.add(key);
      return true;
    })
    .join(" ");
}

async function exactShippingLookup(code, name, brand, env) {
  const cleanCode = String(code || "").replace(/\D/g, "");
  const product = {
    name: String(name || ""),
    brand: String(brand || ""),
    product_code: String(code || ""),
  };

  if (cleanCode.length >= 8) {
    const codeItems = await fetchIncludedItems(cleanCode, env, 1);
    const codeBest = chooseSafeItem(codeItems, product);
    if (codeBest) {
      return {
        shipping_included_price: codeBest.item.price,
        shipping_included_url: codeBest.item.url,
        shipping_included_shop: codeBest.item.shop,
        shipping_included_image: codeBest.item.image,
        shipping_match_score: codeBest.score,
        shipping_match_name: codeBest.item.name,
        sale_quantity_label: codeBest.item.sale_quantity_label,
        lookup_method: "product_code_verified",
      };
    }
    await sleep(1100);
  }

  const keyword = fallbackKeyword(product.name, product.brand);
  if (keyword.length < 2) return null;
  const nameItems = await fetchIncludedItems(keyword, env, 1);
  const best = chooseSafeItem(nameItems, product);
  if (!best) return null;
  return {
    shipping_included_price: best.item.price,
    shipping_included_url: best.item.url,
    shipping_included_shop: best.item.shop,
    shipping_included_image: best.item.image,
    shipping_match_score: best.score,
    shipping_match_name: best.item.name,
    sale_quantity_label: best.item.sale_quantity_label,
    lookup_method: "product_name_specs_verified",
  };
}

function json(data, status = 200, origin = "") {
  const headers = new Headers({
    "Content-Type": "application/json; charset=utf-8",
    "Vary": "Origin",
    "Access-Control-Allow-Methods": "GET, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
  });
  if (!origin || origin === ALLOWED_ORIGIN) headers.set("Access-Control-Allow-Origin", ALLOWED_ORIGIN);
  if (status === 200) headers.set("Cache-Control", "public, max-age=0, s-maxage=300, stale-while-revalidate=1800");
  return new Response(JSON.stringify(data), { status, headers });
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const origin = request.headers.get("Origin") || "";

    if (request.method === "OPTIONS") {
      return new Response(null, {
        status: 204,
        headers: {
          "Access-Control-Allow-Origin": ALLOWED_ORIGIN,
          "Access-Control-Allow-Methods": "GET, OPTIONS",
          "Access-Control-Allow-Headers": "Content-Type",
          "Vary": "Origin",
        },
      });
    }
    if (request.method !== "GET") return json({ error: "method_not_allowed" }, 405, origin);
    if (origin && origin !== ALLOWED_ORIGIN) return json({ error: "origin_not_allowed" }, 403, origin);

    if (url.pathname === "/" || url.pathname === "/health") {
      return json({ ok: true, service: "daily-cost-api", platform: "cloudflare-workers", matching: "safe-images" }, 200, origin);
    }

    if (!env.RAKUTEN_APPLICATION_ID || !env.RAKUTEN_ACCESS_KEY) {
      return json({ error: "server_not_configured" }, 503, origin);
    }

    if (url.pathname === "/api/item-lookup") {
      const itemUrl = String(url.searchParams.get("url") || "").trim();
      const q = String(url.searchParams.get("q") || "").trim();
      const itemCode = String(url.searchParams.get("itemCode") || "").trim();
      if (!canonicalRakutenItemUrl(itemUrl)) return json({ error: "invalid_rakuten_item_url" }, 400, origin);
      try {
        const result = await exactItemLookup(itemUrl, q, itemCode, env);
        return json(result || { found: false, reason: "exact_item_not_found" }, 200, origin);
      } catch (error) {
        console.error("item-lookup failed", error);
        return json({ found: false, error: "rakuten_api_error" }, 502, origin);
      }
    }
    if (url.pathname === "/api/shipping-lookup") {
      const code = String(url.searchParams.get("code") || "").trim();
      const name = String(url.searchParams.get("name") || "").trim();
      const brand = String(url.searchParams.get("brand") || "").trim();
      if (!code && name.length < 2) return json({ error: "product_required" }, 400, origin);
      try {
        const result = await exactShippingLookup(code, name, brand, env);
        return json({ found: Boolean(result), ...(result || {}) }, 200, origin);
      } catch (error) {
        console.error("shipping-lookup failed", error);
        return json({ found: false, error: "rakuten_api_error" }, 502, origin);
      }
    }

    if (url.pathname !== "/api/product-search") return json({ error: "not_found" }, 404, origin);

    const q = String(url.searchParams.get("q") || "").trim();
    const page = Math.max(1, Math.min(100, safeInt(url.searchParams.get("page"), 1)));
    const hits = Math.max(1, Math.min(30, safeInt(url.searchParams.get("hits"), 20)));
    if (q.length < 2) return json({ error: "query_too_short", message: "2文字以上で検索してください。" }, 400, origin);

    try {
      const productResult = await fetchProductCandidates(q, page, hits, env);
      await sleep(1100);

      let includedItems = [];
      try {
        includedItems = await fetchIncludedItemPages(q, env, 3);
      } catch (error) {
        console.error("included item lookup failed", error);
      }

      const products = attachShipping(productResult.products, includedItems)
        .sort((a, b) => Number(Boolean(b.shipping_included_price)) - Number(Boolean(a.shipping_included_price)));

      return json({
        query: q,
        page,
        hits,
        count: products.length,
        page_count: productResult.pageCount,
        total_count: productResult.totalCount,
        shipping_lookup_count: includedItems.length,
        products,
      }, 200, origin);
    } catch (error) {
      console.error("product-search failed", error);
      return json({ error: "rakuten_api_error" }, 502, origin);
    }
  },
};
