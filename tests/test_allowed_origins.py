"""Tests for `[server] allowed_origins` (app.allowed_origins_for + middleware).

The security middleware refuses any POST whose `Origin` header is not in the
allowed set. Until now that set was hard-coded to the two loopback origins,
so reaching the UI through a tunnel or reverse proxy loaded the page but
broke every POST (rules panel, uploads, schedules). These tests pin the
contract of the helper the middleware now reads from, then exercise the
middleware itself over HTTP on a throwaway app.
"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import app  # noqa: E402

try:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
except ImportError:  # pragma: no cover - exercised only where deps are missing
    FastAPI = TestClient = None


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


@unittest.skipIf(TestClient is None, "fastapi/httpx not installed")
class SecurityMiddlewareOriginTests(unittest.TestCase):
    """The middleware, over HTTP, with a valid session token."""

    TOKEN = "test-session-token"
    TUNNEL = "https://poste.tailnet.ts.net"

    def setUp(self):
        test_app = FastAPI()

        @test_app.post("/api/ping")
        async def ping():
            return {"ok": True}

        cfg = {"server": {"port": 8300, "allowed_origins": [self.TUNNEL]}}
        app._install_security_middleware(self.TOKEN, cfg, target=test_app)
        self.client = TestClient(test_app)

    def post(self, origin: str | None, token: str = TOKEN):
        headers = {"X-Session-Token": token}
        if origin is not None:
            headers["Origin"] = origin
        return self.client.post("/api/ping", headers=headers)

    def test_configured_origin_is_accepted(self):
        response = self.post(self.TUNNEL)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"ok": True})

    def test_loopback_origin_is_still_accepted(self):
        self.assertEqual(self.post("http://localhost:8300").status_code, 200)

    def test_unknown_origin_is_refused(self):
        response = self.post("https://evil.example.com")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json(), {"error": "forbidden: origin not allowed"})

    def test_origin_header_is_normalized_before_comparison(self):
        self.assertEqual(self.post(self.TUNNEL.upper() + "/").status_code, 200)

    def test_request_without_origin_relies_on_the_token_alone(self):
        self.assertEqual(self.post(None).status_code, 200)
        self.assertEqual(self.post(None, token="wrong").status_code, 403)

    def test_allowed_origin_does_not_bypass_the_token_check(self):
        response = self.post(self.TUNNEL, token="wrong")
        self.assertEqual(response.status_code, 403)
        self.assertIn("session token", response.json()["error"])


if __name__ == "__main__":
    unittest.main()
