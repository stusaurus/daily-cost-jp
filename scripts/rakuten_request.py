"""Bounded retries for transient Rakuten HTTP failures; never relax validation."""
import json
import math
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import time
import urllib.error
import urllib.request


def fetch_json(request, opener=None, pause=None):
    opener = opener or urllib.request.urlopen
    pause = pause or time.sleep
    for attempt in range(3):
        try:
            with opener(request, timeout=30) as response:
                return json.loads(response.read().decode('utf-8'))
        except urllib.error.HTTPError as exc:
            if exc.code not in (429, 500, 502, 503, 504) or attempt == 2:
                raise
            delay = attempt + 1
            if exc.code == 429:
                delay = 30 * (attempt + 1)
                retry_after = (exc.headers or {}).get('Retry-After')
                if retry_after:
                    try:
                        delay = float(retry_after)
                    except ValueError:
                        try:
                            delay = (parsedate_to_datetime(retry_after) - datetime.now(timezone.utc)).total_seconds()
                        except (ValueError, TypeError):
                            pass
                # Long provider cooldowns stop this build rather than ignoring them.
                if not math.isfinite(delay) or delay > 60:
                    raise
                delay = max(1, delay)
            pause(delay)
