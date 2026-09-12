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
