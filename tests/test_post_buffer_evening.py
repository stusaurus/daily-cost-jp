from __future__ import annotations

import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock
from zoneinfo import ZoneInfo

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import post_buffer_evening as evening


JST = ZoneInfo("Asia/Tokyo")


class EveningXDelayTests(unittest.TestCase):
    def test_after_midnight_uses_previous_evening_refresh(self):
        now = datetime(2026, 10, 16, 0, 11, tzinfo=JST)
        self.assertEqual(
            evening.required_evening_refresh_time(now),
            datetime(2026, 10, 15, 19, 0, tzinfo=JST),
        )

    def test_daytime_run_uses_same_day_refresh(self):
        now = datetime(2026, 10, 16, 20, 0, tzinfo=JST)
        self.assertEqual(
            evening.required_evening_refresh_time(now),
            datetime(2026, 10, 16, 19, 0, tzinfo=JST),
        )

    def test_main_requests_payload_for_refresh_date(self):
        refresh = datetime(2026, 10, 15, 19, 0, tzinfo=JST)
        payload = {"date": "2026-10-15", "items": [{"id": "tissue"}]}
        with (
            mock.patch.object(evening, "required_evening_refresh_time", return_value=refresh),
            mock.patch.object(evening.buffer, "fetch_today_social", return_value=payload) as fetch,
            mock.patch.object(evening, "build_evening_text", return_value="post"),
            mock.patch.object(
                evening.buffer,
                "discover_x_channel",
                return_value=("org", "name", {"id": "channel", "service": "twitter", "name": "nichiyo_cost"}),
            ),
            mock.patch.object(evening.buffer, "was_already_posted", return_value=True),
        ):
            evening.main()

        fetch.assert_called_once_with(
            not_before=refresh,
            expected_date="2026-10-15",
            allow_newer=True,
        )

    def test_main_skips_when_next_day_payload_is_already_live(self):
        refresh = datetime(2026, 10, 15, 19, 0, tzinfo=JST)
        payload = {"date": "2026-10-16", "text": "newer", "items": [{"id": "tissue"}]}
        with (
            mock.patch.object(evening, "required_evening_refresh_time", return_value=refresh),
            mock.patch.object(evening.buffer, "fetch_today_social", return_value=payload),
            mock.patch.object(evening, "build_evening_text") as build_text,
            mock.patch.object(evening.buffer, "discover_x_channel") as discover,
        ):
            evening.main()

        build_text.assert_not_called()
        discover.assert_not_called()


if __name__ == "__main__":
    unittest.main()

