"""Bounded retries for transient Rakuten HTTP failures; never relax validation."""
import json
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
            if exc.code not in (500, 502, 503, 504) or attempt == 2:
                raise
            pause(attempt + 1)
