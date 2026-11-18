"""One-time, explicitly approved X traffic experiment via the existing Buffer channel."""
from __future__ import annotations

import os
import post_buffer as buffer

URL = ("https://stusaurus.github.io/daily-cost-jp/categories/toilet-paper/"
       "?utm_source=x&utm_medium=social&utm_campaign=paper_length_20261118"
       "&utm_content=length_vs_roll")
TEXT = (
    "トイレットペーパー、12ロール同士でも巻きの長さが違うと安さは逆転します。\n"
    "私が運営する比較サイトでは、シングル・ダブルを分けて"
    "「10mあたりの価格」と「送料込みの支払総額」を確認できます。\n"
    "買い替え前の比較にどうぞ。\n"
    "※アフィリエイト広告を含みます。価格・在庫・地域別送料は購入先で確認してください。\n"
    + URL
)


def main() -> None:
    if len(TEXT) > 280:
        buffer.fail(f"Post exceeds standard X character budget: {len(TEXT)}")
    # Dry-run never touches Buffer credentials or remote APIs.
    if os.environ.get("PAPER_X_CONFIRM") != "PUBLISH_PAPER_EXPERIMENT":
        print("DRY RUN: no X post sent.\n" + TEXT)
        return
    org_id, _, channel = buffer.discover_x_channel()
    if buffer.normalize_name(channel.get("name")) != "nichiyo_cost":
        buffer.fail("Refusing to post to an unexpected X channel")
    channel_id = str(channel.get("id") or "")
    if buffer.was_already_posted(org_id, channel_id, TEXT):
        print("SKIP: exact post already exists in Buffer")
        return
    buffer.publish_now(channel_id, TEXT)


if __name__ == "__main__":
    main()
