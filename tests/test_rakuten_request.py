import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, MagicMock
from urllib.error import HTTPError
sys.path.insert(0,str(Path(__file__).parents[1]/'scripts'))
from rakuten_request import fetch_json

class RakutenRequestTests(unittest.TestCase):
    def test_transient_502_recovers_without_changing_data(self):
        response=MagicMock();response.__enter__.return_value.read.return_value=b'{"Items":[{"itemPrice":100}]}'
        opener=Mock(side_effect=[HTTPError('https://example.test',502,'Bad Gateway',{},None),response]);pause=Mock()
        self.assertEqual(fetch_json('request',opener,pause),{'Items':[{'itemPrice':100}]})
        self.assertEqual(opener.call_count,2);pause.assert_called_once_with(1)
    def test_repeated_failure_is_bounded_and_propagated(self):
        opener=Mock(side_effect=HTTPError('https://example.test',503,'Unavailable',{},None));pause=Mock()
        with self.assertRaises(HTTPError):fetch_json('request',opener,pause)
        self.assertEqual(opener.call_count,3);self.assertEqual(pause.call_count,2)
    def test_invalid_requests_are_not_retried(self):
        for code in (400,401):
            opener=Mock(side_effect=HTTPError('https://example.test',code,'error',{},None));pause=Mock()
            with self.assertRaises(HTTPError):fetch_json('request',opener,pause)
            self.assertEqual(opener.call_count,1);pause.assert_not_called()

    def test_rate_limit_waits_for_provider_before_bounded_retry(self):
        response=MagicMock();response.__enter__.return_value.read.return_value=b'{"Items":[]}'
        opener=Mock(side_effect=[HTTPError('https://example.test',429,'rate limited',{'Retry-After':'12'},None),response]);pause=Mock()
        self.assertEqual(fetch_json('request',opener,pause),{'Items':[]})
        pause.assert_called_once_with(12)
    def test_long_provider_cooldown_stops_the_build(self):
        opener=Mock(side_effect=HTTPError('https://example.test',429,'rate limited',{'Retry-After':'120'},None));pause=Mock()
        with self.assertRaises(HTTPError):fetch_json('request',opener,pause)
        self.assertEqual(opener.call_count,1);pause.assert_not_called()
    def test_rate_limit_without_header_cools_down_and_still_stops(self):
        opener=Mock(side_effect=HTTPError('https://example.test',429,'rate limited',{},None));pause=Mock()
        with self.assertRaises(HTTPError):fetch_json('request',opener,pause)
        self.assertEqual(opener.call_count,3)
        self.assertEqual([c.args[0] for c in pause.call_args_list],[30,60])
