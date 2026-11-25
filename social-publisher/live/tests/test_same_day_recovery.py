"""Offline same-day recovery protections. Never calls a real Meta API."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.parse import parse_qs

BASE = Path(__file__).resolve().parents[3]
sys.path.insert(0,str(BASE/"social-publisher"))
sys.path.insert(0,str(BASE/"social-publisher/live"))

from asset_reader import fetch_pinned_pair, AssetRejected
from facebook_once import publish_once, APPROVAL_PHRASE
from test_facebook_once import FakeMeta, asset, COMMIT, SECRET, NOW, ENV
from publish_cli import main as publisher_main


class Response:
    def __init__(self, payload=b"test"):
        self.payload = payload
    def __enter__(self):
        return self
    def __exit__(self,*_):
        return False
    def read(self,n):
        return self.payload[:n]


class SameDayRecoveryTests(unittest.TestCase):
    def test_pinned_recovery_uses_exact_dedicated_paths(self):
        urls=[]
        def get(request, timeout):
            urls.append(request.full_url)
            return Response()
        with patch("asset_reader.urlopen",side_effect=get):
            fetch_pinned_pair(commit_sha=COMMIT,date_sast="2026-11-25",recovery=True)
        self.assertEqual(urls,[
            f"https://raw.githubusercontent.com/Draztik99/coinoswap/{COMMIT}/docs/daily-rates/recovery/2026-11-25.json",
            f"https://raw.githubusercontent.com/Draztik99/coinoswap/{COMMIT}/docs/daily-rates/recovery/2026-11-25.png",
        ])
        with self.assertRaises(AssetRejected):
            fetch_pinned_pair(commit_sha="../bad",date_sast="2026-11-25",recovery=True)

    def test_recovery_sender_uses_fresh_pinned_image_not_original(self):
        meta=FakeMeta()
        ledger=Mock()
        ledger.reserve.return_value="coinoswap-facebook-daily-rates-2026-11-25"
        result=publish_once(asset(),pinned_commit=COMMIT,token=SECRET,
                            environ=ENV,approval_phrase=APPROVAL_PHRASE,
                            reservation=ledger,opener=meta,clock=lambda:NOW,
                            recovery=True)
        self.assertEqual(result.status,"PUBLISHED")
        requests=[r for r,_ in meta.requests if r.get_method()=="POST"]
        self.assertEqual(len(requests),1)
        image=parse_qs(requests[0].data.decode())["url"][0]
        self.assertEqual(image,
            f"https://raw.githubusercontent.com/Draztik99/coinoswap/{COMMIT}/docs/daily-rates/recovery/2026-11-25.png")
        ledger.reserve.assert_called_once_with("2026-11-25")

    def test_recovery_flag_must_be_explicitly_authorized(self):
        result=publisher_main(["--publish","--recovery","--commit-sha",COMMIT],
                 env={"GITHUB_REF":"refs/heads/main","GITHUB_REPOSITORY":"Draztik99/coinoswap"})
        self.assertEqual(result,2)

    def test_recovery_workflow_is_strictly_manual_and_preserves_original(self):
        path=BASE/".github/workflows/facebook-same-day-recovery.yml"
        s=path.read_text(encoding="utf-8")
        self.assertIn("  workflow_dispatch:",s)
        self.assertNotIn("  schedule:",s)
        self.assertNotIn("  push:",s)
        self.assertIn('environment: facebook-live',s)
        self.assertIn("COINOSWAP_RATES_RECOVERY:",s)
        self.assertIn("COINOSWAP_FB_RECOVERY_ENABLED:",s)
        self.assertIn("publish_cli.py --publish --recovery",s)
        self.assertIn("set -o pipefail",s)
        self.assertIn('refs/tags/coinoswap-facebook-daily-rates-$day',s)
        self.assertIn('docs/daily-rates/recovery/$day.png',s)
        self.assertIn("publication_receipt.py --recovery",s)
        self.assertNotIn('git push --force',s)


if __name__=="__main__":
    unittest.main()
