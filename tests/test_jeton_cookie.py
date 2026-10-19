"""Cookie de session : le navigateur s'authentifie sans jeton dans l'URL (lot claude-1, msg 4867).

EventSource et WebSocket ne posent pas d'en-tête ; un ?token= finit dans l'historique, les journaux et le
Referer. La page (/, /atelier) pose un cookie HttpOnly; Secure; SameSite=Strict, nommé d'après le port, que le
middleware et le WebSocket acceptent EN PLUS de l'en-tête et du ?token= (agents, scripts). Le dual : un cookie
faux, un cookie d'une autre salle (autre port) ou une origine étrangère restent refusés.
"""

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app  # noqa: E402

JETON = "a" * 64
PORT = 8399


class CookieSessionTests(unittest.TestCase):
    def setUp(self):
        for nom in ("session_token", "cookie_session", "origines_permises"):
            self.addCleanup(setattr, app, nom, getattr(app, nom))
        # Une app neuve, avec le vrai middleware : l'app globale ne reçoit pas de middleware après démarrage.
        self.cible = FastAPI()

        @self.cible.get("/api/v2/flux")
        async def flux():
            return {"ok": True}

        app._install_security_middleware(JETON, {"server": {"port": PORT}}, cible=self.cible)
        self.client = TestClient(self.cible, base_url="https://salle.test")
        self.addCleanup(self.client.close)

    def get(self, **kw):
        self.client.cookies.clear()
        return self.client.get("/api/v2/flux", **kw)

    def test_la_page_pose_un_cookie_httponly_secure_samesite_strict_nomme_d_apres_le_port(self):
        entete = app.poser_cookie_session(HTMLResponse("<p>x</p>")).headers["set-cookie"]
        self.assertTrue(entete.startswith(f"agentchattr_session_{PORT}={JETON};"), entete)
        for attribut in ("HttpOnly", "Secure", "SameSite=strict", "Path=/"):
            self.assertIn(attribut.lower(), entete.lower())

    def test_le_cookie_de_session_suffit_sans_jeton_dans_l_url(self):
        r = self.get(cookies={f"agentchattr_session_{PORT}": JETON})
        self.assertEqual(r.status_code, 200, r.text)

    def test_le_dual_un_cookie_faux_est_refuse(self):
        self.assertEqual(self.get(cookies={f"agentchattr_session_{PORT}": "b" * 64}).status_code, 403)

    def test_le_dual_le_cookie_d_une_autre_salle_est_refuse(self):
        self.assertEqual(self.get(cookies={"agentchattr_session_8300": JETON}).status_code, 403)

    def test_le_dual_sans_rien_refuse(self):
        self.assertEqual(self.get().status_code, 403)

    def test_un_jeton_non_ascii_est_refuse_sans_erreur_500(self):
        self.assertEqual(self.get(params={"token": "é" * 4}).status_code, 403)

    def test_les_agents_et_scripts_gardent_l_en_tete_et_le_token_en_query(self):
        self.assertEqual(self.get(headers={"x-session-token": JETON}).status_code, 200)
        self.assertEqual(self.get(params={"token": JETON}).status_code, 200)

    def test_le_dual_une_origine_etrangere_est_refusee_meme_avec_le_cookie(self):
        r = self.get(cookies={f"agentchattr_session_{PORT}": JETON}, headers={"origin": "https://evil.example"})
        self.assertEqual(r.status_code, 403)


class WebSocketCookieTests(unittest.TestCase):
    """La garde du WebSocket /ws : jeton en query ou cookie ; origine étrangère refusée."""

    def setUp(self):
        for nom in ("session_token", "cookie_session", "origines_permises"):
            self.addCleanup(setattr, app, nom, getattr(app, nom))
        app._install_security_middleware(JETON, {"server": {"port": PORT}}, cible=FastAPI())

    def garde(self, query=None, cookies=None, origine=None):
        ws = SimpleNamespace(query_params=query or {}, cookies=cookies or {},
                             headers={"origin": origine} if origine else {})
        return app._ws_autorise(ws)

    def test_cookie_ou_query_acceptes(self):
        self.assertTrue(self.garde(cookies={f"agentchattr_session_{PORT}": JETON}, origine=f"http://127.0.0.1:{PORT}"))
        self.assertTrue(self.garde(query={"token": JETON}))

    def test_le_dual_cookie_faux_ou_absent_refuse(self):
        self.assertFalse(self.garde(cookies={f"agentchattr_session_{PORT}": "b" * 64}))
        self.assertFalse(self.garde())

    def test_le_dual_origine_etrangere_refusee(self):
        self.assertFalse(self.garde(cookies={f"agentchattr_session_{PORT}": JETON}, origine="https://evil.example"))


if __name__ == "__main__":
    unittest.main()
