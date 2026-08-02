from __future__ import annotations

import hashlib
import hmac
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import run_databento_flow_monitor as publisher


class _Response:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return b'{"accepted":{"flow":1}}'


class MarketRiskPublisherTests(unittest.TestCase):
    def test_publish_signs_exact_body_without_sending_secret(self):
        captured = {}

        def fake_open(request, timeout):
            captured["request"] = request
            captured["timeout"] = timeout
            return _Response()

        with mock.patch.object(publisher.time, "time", return_value=1_722_866_400), \
             mock.patch.object(publisher.secrets, "token_hex", return_value="a" * 32), \
             mock.patch.object(publisher.urllib.request, "urlopen", side_effect=fake_open):
            result = publisher.publish(
                "https://example.test/ingest", "s" * 32, [{"symbol": "SPY"}],
                [{"component": "databento_liquidity"}],
            )

        request = captured["request"]
        headers = {key.lower(): value for key, value in request.header_items()}
        self.assertNotIn("authorization", headers)
        self.assertNotIn("s" * 32, json.dumps(headers))
        self.assertEqual(headers["x-market-risk-timestamp"], "1722866400")
        self.assertEqual(headers["x-market-risk-nonce"], "a" * 32)
        expected = hmac.new(
            ("s" * 32).encode(),
            b"1722866400\n" + ("a" * 32).encode() + b"\n" + request.data,
            hashlib.sha256,
        ).hexdigest()
        self.assertEqual(headers["x-market-risk-signature"], expected)
        body = json.loads(request.data)
        self.assertEqual(body["components"][0]["component"], "databento_liquidity")
        self.assertEqual(result["accepted"]["flow"], 1)


if __name__ == "__main__":
    unittest.main()
