"""Tests for `[server] allowed_origins` (app.allowed_origins_for).

The security middleware refuses any POST whose `Origin` header is not in the
allowed set. Until now that set was hard-coded to the two loopback origins,
so reaching the UI through a tunnel or reverse proxy loaded the page but
broke every POST (rules panel, uploads, schedules). These tests pin the
contract of the helper the middleware now reads from.
"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import app  # noqa: E402


class AllowedOriginsTests(unittest.TestCase):
    def test_loopback_origins_are_always_allowed(self):
        self.assertEqual(
            app.allowed_origins_for({"server": {"port": 8300}}),
            {"http://127.0.0.1:8300", "http://localhost:8300"},
        )

    def test_loopback_origins_follow_the_configured_port(self):
        origins = app.allowed_origins_for({"server": {"port": 9999}})
        self.assertIn("http://localhost:9999", origins)
        self.assertNotIn("http://localhost:8300", origins)

    def test_missing_config_falls_back_to_the_default_port(self):
        self.assertIn("http://127.0.0.1:8300", app.allowed_origins_for({}))

    def test_extra_origins_are_added_to_the_loopback_ones(self):
        cfg = {"server": {"port": 8300, "allowed_origins": ["https://poste.tailnet.ts.net"]}}
        origins = app.allowed_origins_for(cfg)
        self.assertIn("https://poste.tailnet.ts.net", origins)
        self.assertIn("http://127.0.0.1:8300", origins)

    def test_extra_origins_are_normalized(self):
        cfg = {"server": {"allowed_origins": ["  HTTPS://Poste.Tailnet.ts.net/  "]}}
        self.assertIn("https://poste.tailnet.ts.net", app.allowed_origins_for(cfg))

    def test_a_single_string_is_accepted_as_one_origin(self):
        cfg = {"server": {"allowed_origins": "https://chat.example.ca"}}
        self.assertIn("https://chat.example.ca", app.allowed_origins_for(cfg))

    def test_entries_without_a_scheme_are_ignored(self):
        cfg = {"server": {"allowed_origins": ["poste.tailnet.ts.net", "", "https://", 42, None]}}
        self.assertEqual(
            app.allowed_origins_for(cfg),
            {"http://127.0.0.1:8300", "http://localhost:8300"},
        )

    def test_a_non_list_value_is_ignored(self):
        cfg = {"server": {"allowed_origins": {"bad": "shape"}}}
        self.assertEqual(
            app.allowed_origins_for(cfg),
            {"http://127.0.0.1:8300", "http://localhost:8300"},
        )


if __name__ == "__main__":
    unittest.main()
