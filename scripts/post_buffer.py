"""Publish the latest daily-deals social payload to X through Buffer.

This script is intended for GitHub Actions after the Pages deployment succeeds.
It discovers the connected X channel from the Buffer account, waits until the
public social payload is from today (JST), avoids duplicate posts, and then
publishes immediately.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

BUFFER_API = "https://api.buffer.com"
SOCIAL_PAYLOAD_URL = os.environ.get(
    "SOCIAL_PAYLOAD_URL",
    "https://stusaurus.github.io/daily-cost-jp/social/latest.json",
)
TARGET_CHANNEL = os.environ.get("BUFFER_CHANNEL_NAME", "nichiyo_cost").strip().lower()
JST = ZoneInfo("Asia/Tokyo")
PLAIN_TODAY_URL = "https://stusaurus.github.io/daily-cost-jp/today/"
TRACKED_TODAY_URL = (
    PLAIN_TODAY_URL
    + "?utm_source=x&utm_medium=social&utm_campaign=daily_deals&utm_content=daily_post"
)


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def gql(query: str) -> dict:
    api_key = os.environ.get("BUFFER_API_KEY", "").strip()
    if not api_key:
        fail("BUFFER_API_KEY is not set")

    body = json.dumps({"query": query}).encode("utf-8")
    request = urllib.request.Request(
        BUFFER_API,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "daily-cost-jp-github-actions/1.0",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        fail(f"Buffer API HTTP {exc.code}: {detail[:800]}")
    except Exception as exc:
        fail(f"Buffer API request failed: {exc}")

    if payload.get("errors"):
        fail(f"Buffer GraphQL error: {json.dumps(payload['errors'], ensure_ascii=False)[:1200]}")
    return payload.get("data") or {}


def fetch_today_social() -> dict:
    expected_date = datetime.now(JST).date().isoformat()
    last_date = None

    # Pages is usually updated immediately after deployment, but give its CDN a
    # short window to expose the new social payload before posting.
    for attempt in range(12):
        separator = "&" if "?" in SOCIAL_PAYLOAD_URL else "?"
        url = f"{SOCIAL_PAYLOAD_URL}{separator}v={int(time.time())}"
        request = urllib.request.Request(
            url,
            headers={
                "Cache-Control": "no-cache",
                "User-Agent": "daily-cost-jp-github-actions/1.0",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                payload = json.loads(response.read().decode("utf-8"))
            last_date = payload.get("date")
            if last_date == expected_date and str(payload.get("text") or "").strip():
                return payload
        except Exception as exc:
            print(f"Social payload attempt {attempt + 1}/12 failed: {exc}")

        if attempt < 11:
            print(
                f"Waiting for today's Pages payload: expected={expected_date}, got={last_date}"
            )
            time.sleep(15)

    fail(
        f"Today's social payload was not available after deployment "
        f"(expected {expected_date}, got {last_date})"
    )
    return {}


def normalize_name(value: object) -> str:
    return str(value or "").strip().lower().lstrip("@")


def discover_x_channel() -> tuple[str, str, dict]:
    data = gql(
        """
        query GetOrganizations {
          account {
            organizations {
              id
              name
            }
          }
        }
        """
    )
    organizations = ((data.get("account") or {}).get("organizations") or [])
    if not organizations:
        fail("No Buffer organization was found")

    x_channels: list[tuple[str, str, dict]] = []
    exact: list[tuple[str, str, dict]] = []

    for organization in organizations:
        org_id = str(organization.get("id") or "")
        org_name = str(organization.get("name") or "")
        if not org_id:
            continue
        query = f'''
        query GetChannels {{
          channels(input: {{ organizationId: {json.dumps(org_id)} }}) {{
            id
            name
            service
          }}
        }}
        '''
        channel_data = gql(query)
        for channel in channel_data.get("channels") or []:
            service = normalize_name(channel.get("service"))
            if service not in {"twitter", "x"}:
                continue
            item = (org_id, org_name, channel)
            x_channels.append(item)
            if normalize_name(channel.get("name")) == TARGET_CHANNEL:
                exact.append(item)

    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        fail(f"Multiple X channels matched @{TARGET_CHANNEL}")
    if len(x_channels) == 1:
        return x_channels[0]

    available = ", ".join(normalize_name(c.get("name")) for _, _, c in x_channels)
    fail(f"Could not uniquely find X channel @{TARGET_CHANNEL}; available X channels: {available or 'none'}")
    raise AssertionError


def final_post_text(payload: dict) -> str:
    text = str(payload.get("text") or "").strip()
    # Attribute every automated X visit in GA4 without changing the public page URL.
    text = text.replace(PLAIN_TODAY_URL, TRACKED_TODAY_URL)
    disclosure = "※楽天アフィリエイトを利用しています"
    if disclosure not in text:
        text = f"{text}\n{disclosure}"
    if len(text) > 280:
        # Current generated copy is intentionally short, but fail safely rather
        # than silently changing a live social post if it ever grows too long.
        fail(f"Generated X post is {len(text)} characters; expected <= 280")
    return text


def was_already_posted(org_id: str, channel_id: str, text: str) -> bool:
    query = f'''
    query RecentPosts {{
      posts(
        first: 100
        input: {{
          organizationId: {json.dumps(org_id)}
          filter: {{ status: [sent, scheduled, sending], channelIds: [{json.dumps(channel_id)}] }}
          sort: [{{ field: createdAt, direction: desc }}]
        }}
      ) {{
        edges {{
          node {{
            id
            text
            status
            createdAt
            channelId
          }}
        }}
      }}
    }}
    '''
    data = gql(query)
    edges = ((data.get("posts") or {}).get("edges") or [])
    for edge in edges:
        node = edge.get("node") or {}
        if str(node.get("text") or "").strip() == text:
            print(f"Today's X post already exists in Buffer: {node.get('id')}")
            return True
    return False


def publish_now(channel_id: str, text: str) -> None:
    query = f'''
    mutation PublishDailyPost {{
      createPost(input: {{
        text: {json.dumps(text, ensure_ascii=False)}
        channelId: {json.dumps(channel_id)}
        schedulingType: automatic
        mode: shareNow
      }}) {{
        __typename
        ... on PostActionSuccess {{
          post {{
            id
            text
            status
            dueAt
          }}
        }}
        ... on MutationError {{
          message
        }}
      }}
    }}
    '''
    data = gql(query)
    result = data.get("createPost") or {}
    if result.get("__typename") == "PostActionSuccess":
        post = result.get("post") or {}
        print(f"Published daily X post through Buffer: id={post.get('id')} status={post.get('status')}")
        return
    fail(f"Buffer rejected the post: {result.get('message') or json.dumps(result, ensure_ascii=False)}")


def main() -> None:
    payload = fetch_today_social()
    text = final_post_text(payload)
    org_id, org_name, channel = discover_x_channel()
    channel_id = str(channel.get("id") or "")
    print(
        f"Target Buffer channel: organization={org_name or org_id}, "
        f"service={channel.get('service')}, name={channel.get('name')}"
    )
    if was_already_posted(org_id, channel_id, text):
        return
    publish_now(channel_id, text)


if __name__ == "__main__":
    main()
