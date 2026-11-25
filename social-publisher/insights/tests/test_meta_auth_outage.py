"""A Meta token outage must not expose secrets or hide stale dashboard data."""
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError

INSIGHTS = Path(__file__).resolve().parents[1]
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(INSIGHTS))
from facebook_collector import collect, CollectorUnavailable


class TokenOutageTests(unittest.TestCase):
    def test_meta_http_status_is_safely_classified(self):
        class FailedPageToken:
            def open(self, request, timeout=12):
                raise HTTPError(request.full_url, 401,
                                "PRIVATE_TOKEN=DO_NOT_ECHO", {}, None)
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(CollectorUnavailable) as exc:
                collect(token="SECRET_FOR_TEST",now=datetime.fromisoformat(
                    "2026-11-24T20:30:00+02:00"),root=Path(tmp),
                    output=Path(tmp)/"out",opener=FailedPageToken())
        self.assertIn("HTTP 401",str(exc.exception))
        self.assertNotIn("DO_NOT_ECHO",str(exc.exception))
        self.assertNotIn("SECRET_FOR_TEST",str(exc.exception))

    def test_analytics_workflow_does_not_suppress_orphaned_reports(self):
        yaml=(ROOT/".github/workflows/coinoswap-social-analytics.yml").read_text()
        self.assertIn('5 14,17,18 * * *',yaml)
        self.assertIn("continue-on-error: true",yaml)
        self.assertIn("id: facebook_collect",yaml)
        self.assertIn("steps.facebook_collect.outcome == 'failure'",yaml)
        self.assertLess(yaml.index("Render black-and-gold dashboard"),
                        yaml.index("Flag failed Meta collection"))
        self.assertNotIn("/photos",yaml)
        self.assertNotIn("metricool.com",yaml)

if __name__=="__main__":
    unittest.main()
