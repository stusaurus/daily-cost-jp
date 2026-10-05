const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const source = fs.readFileSync(
  path.join(__dirname, "..", "cloudflare-api", "src", "safe-index.js"),
  "utf8"
);

test("worker exposes lightweight FISHING lookup route", () => {
  assert.match(source, /\/api\/fishing-item-lookup/);
  assert.match(source, /async function fishingItemLookup\(/);
});

test("FISHING lookup uses shop search and returns candidates", () => {
  const start = source.indexOf("async function fishingItemLookup(");
  const end = source.indexOf("async function exactItemLookup(", start);
  const block = source.slice(start, end);
  assert.match(block, /fetchShopItems\(query, locator\.shopCode, env\)/);
  assert.match(block, /candidates: items\.slice\(0, 30\)/);
  assert.doesNotMatch(block, /fetchExactRakutenPageInfo/);
});

test("FISHING lookup keeps the requested shop as the hard scope", () => {
  const start = source.indexOf("async function fishingItemLookup(");
  const end = source.indexOf("async function exactItemLookup(", start);
  const block = source.slice(start, end);
  assert.match(block, /rakutenItemLocator\(itemUrl\)/);
  assert.match(block, /shop_code: locator\.shopCode/);
});
