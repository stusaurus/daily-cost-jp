"""Yahoo! Shopping v3 client. Credentials and responses stay out of logs."""
import json
import re
import time
from http.client import HTTPException
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, unquote, urlencode, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, build_opener

API = "https://shopping.yahooapis.jp/ShoppingWebService/V3/itemSearch"
VC_HOST = "ck.jp.ap.valuecommerce.com"
REQUEST_INTERVAL = 2.5


class YahooUnavailable(Exception):
    """A safe diagnostic code, without request data or exception details."""


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def safe_url(value):
    if not isinstance(value, str) or re.search(r'[\x00-\x20\x7f<>"\\]', value):
        return None
    try:
        url = urlsplit(value)
        if url.netloc != url.hostname or url.fragment:
            return None
    except ValueError:
        return None
    return url


def affiliate_config(value):
    """Accept the extracted referral URL or the URL-encoded form in the docs."""
    raw = unquote(value.strip())
    url = safe_url(raw)
    params = parse_qs(url.query, keep_blank_values=True) if url else {}
    if (not url or url.scheme not in ("http", "https") or url.hostname != VC_HOST
            or url.path != "/servlet/referral" or set(params) - {"sid", "pid", "vc_url"}
            or not all(len(params.get(k, [])) == 1 and re.fullmatch(r"[0-9]+", params[k][0])
                       for k in ("sid", "pid"))
            or params.get("vc_url", [""]) != [""]):
        raise YahooUnavailable("affiliate_config_format")
    query = urlencode({"sid": params["sid"][0], "pid": params["pid"][0], "vc_url": ""})
    return urlunsplit(url._replace(query=query)), params["sid"][0], params["pid"][0]


def product_target(value, code):
    url = safe_url(value)
    if not url or url.scheme != "https" or not isinstance(code, str):
        return False
    if url.hostname == "store.shopping.yahoo.co.jp":
        match = re.fullmatch(r"/([\w-]+)/([\w.-]+)\.html", url.path, re.ASCII)
        return bool(match and f"{match[1]}_{match[2]}" == code)
    if url.hostname == "lohaco.yahoo.co.jp":
        match = re.fullmatch(r"/store/h-lohaco/item/([\w-]+)/?", url.path, re.ASCII | re.I)
        return bool(match and code.lower() in {f"{store}_{match[1].lower()}"
                                              for store in ("h-lohaco", "rd-lohaco")})
    return False


class YahooShopping:
    def __init__(self, app_id, affiliate_id):
        self._app_id = app_id.strip()
        if not self._app_id:
            raise YahooUnavailable("missing_app_id")
        if not affiliate_id.strip():
            raise YahooUnavailable("missing_affiliate_id")
        self._prefix, self._sid, self._pid = affiliate_config(affiliate_id)
        self._opener = build_opener(NoRedirect())
        self._last_request = float("-inf")
        self._cache = {}
        self._limit = None
        self.requests = 0
        self.cache_hits = 0

    def search(self, *, jan=None, query=None, results=50, shipping=None):
        filters = {"jan_code": jan} if jan else {"query": query}
        params = dict(filters, appid=self._app_id, affiliate_type="vc",
                      affiliate_id=self._prefix, in_stock="true", condition="new",
                      sort="+price" if jan else "-score", results=results)
        if shipping:
            params["shipping"] = shipping
        key = jan, query, results, shipping
        if key in self._cache:
            self.cache_hits += 1
            return self._cache[key]
        if self._limit:
            raise YahooUnavailable(self._limit)
        for attempt in range(2):
            time.sleep(max(0, REQUEST_INTERVAL - (time.monotonic() - self._last_request)))
            self._last_request = time.monotonic()
            self.requests += 1
            try:
                with self._opener.open(f"{API}?{urlencode(params)}", timeout=12) as response:
                    payload = json.loads(response.read(3_000_000))
                break
            except HTTPError as error:
                retry_after = error.headers.get("Retry-After", "") if error.headers else ""
                wait = int(retry_after) if retry_after.isascii() and retry_after.isdigit() and len(retry_after) < 5 else 55
                if error.code != 429 or attempt or wait > 60:
                    if error.code in (401, 403, 429):
                        self._limit = f"http_{error.code}"
                    raise YahooUnavailable(f"http_{error.code}") from None
                time.sleep(max(wait, REQUEST_INTERVAL))
            except (URLError, OSError, ValueError, HTTPException):
                raise YahooUnavailable("network_or_response") from None

        hits = payload.get("hits") if isinstance(payload, dict) else None
        if not isinstance(hits, list) or any(not isinstance(hit, dict) for hit in hits):
            raise YahooUnavailable("response_schema")
        self._cache[key] = hits
        return hits

    def affiliate_link(self, hit):
        value = hit.get("url")
        url = safe_url(value)
        if (not url or url.scheme not in ("https", "http") or url.hostname != VC_HOST
                or url.path != "/servlet/referral"):
            return None
        params = parse_qs(url.query, keep_blank_values=True)
        targets = params.get("vc_url", [])
        if (params.get("sid") != [self._sid] or params.get("pid") != [self._pid]
                or len(targets) != 1 or not product_target(targets[0], hit.get("code"))
                or self._app_id in unquote(value)):
            return None
        # The official example uses HTTP. Publish its HTTPS equivalent.
        return urlunsplit(url._replace(scheme="https"))
