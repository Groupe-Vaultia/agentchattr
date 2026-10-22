"""`[server] allowed_origins` : origines de confiance (tunnel du cellulaire), lues de config.local.toml.

Le middleware de sécurité refuse tout POST dont l'en-tête `Origin` n'est pas permis. Sans ces
origines, la salle s'affiche par le tunnel mais chaque POST échoue (règles, téléversements,
horaires). Repris de la branche `acces/mobile` (21 sept. 2026, revue codex), adapté à
l'implémentation de `main` : `_install_security_middleware(..., cible=)` et `config_loader`.
"""

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import app  # noqa: E402
from config_loader import load_config  # noqa: E402

try:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
except ImportError:  # pragma: no cover - seulement si les dépendances manquent
    FastAPI = TestClient = None

TUNNEL = "https://poste.tailnet.ts.net"
BOUCLE = {"http://127.0.0.1:8300", "http://localhost:8300"}


class _EtatApp(unittest.TestCase):
    """Le middleware écrit des globales du module `app` : on les remet en place après chaque test."""

    def setUp(self):
        noms = ("session_token", "cookie_session", "origines_permises")
        sauve = {n: getattr(app, n, None) for n in noms}
        self.addCleanup(lambda: [setattr(app, n, v) for n, v in sauve.items()])

    def origines(self, cfg):
        app._install_security_middleware("jeton", cfg, cible=FastAPI())
        return set(app.origines_permises)


@unittest.skipIf(FastAPI is None, "fastapi absent")
class OriginesPermisesTests(_EtatApp):
    def test_boucle_locale_toujours_permise(self):
        self.assertEqual(self.origines({"server": {"port": 8300}}), BOUCLE)

    def test_boucle_suit_le_port(self):
        o = self.origines({"server": {"port": 9999}})
        self.assertIn("http://localhost:9999", o)
        self.assertNotIn("http://localhost:8300", o)

    def test_origine_configuree_ajoutee_sans_barre_finale(self):
        o = self.origines({"server": {"port": 8300, "allowed_origins": [TUNNEL + "/", "  "]}})
        self.assertEqual(o, BOUCLE | {TUNNEL})

    def test_une_chaine_seule_est_une_origine(self):
        o = self.origines({"server": {"port": 8300, "allowed_origins": TUNNEL}})
        self.assertEqual(o, BOUCLE | {TUNNEL})

    def test_valeurs_non_textuelles_ignorees(self):
        self.assertEqual(self.origines({"server": {"port": 8300, "allowed_origins": [42, None]}}), BOUCLE)


@unittest.skipIf(TestClient is None, "fastapi/httpx absents")
class MiddlewareOrigineTests(_EtatApp):
    """Le middleware, en HTTP, sur une app jetable."""

    JETON = "jeton-de-test"

    def setUp(self):
        super().setUp()
        cible = FastAPI()

        @cible.post("/api/ping")
        async def ping():
            return {"ok": True}

        app._install_security_middleware(self.JETON, {"server": {"port": 8300, "allowed_origins": [TUNNEL]}}, cible=cible)
        self.client = TestClient(cible)

    def post(self, origine, jeton=JETON):
        entetes = {"X-Session-Token": jeton}
        if origine is not None:
            entetes["Origin"] = origine
        return self.client.post("/api/ping", headers=entetes)

    def test_origine_configuree_acceptee(self):
        r = self.post(TUNNEL)
        self.assertEqual((r.status_code, r.json()), (200, {"ok": True}))

    def test_boucle_encore_acceptee(self):
        self.assertEqual(self.post("http://localhost:8300").status_code, 200)

    def test_origine_inconnue_refusee(self):
        r = self.post("https://evil.example.com")
        self.assertEqual((r.status_code, r.json()), (403, {"error": "forbidden: origin not allowed"}))

    def test_sans_origine_le_jeton_seul_decide(self):
        self.assertEqual(self.post(None).status_code, 200)
        self.assertEqual(self.post(None, jeton="faux").status_code, 403)

    def test_origine_permise_ne_dispense_pas_du_jeton(self):
        r = self.post(TUNNEL, jeton="faux")
        self.assertEqual(r.status_code, 403)
        self.assertIn("session token", r.json()["error"])


class ChargementConfigTests(unittest.TestCase):
    """config.local.toml (hors git) ajoute ses origines à celles de config.toml."""

    def charger(self, local: str | None):
        with tempfile.TemporaryDirectory() as d:
            racine = Path(d)
            (racine / "config.toml").write_text('[server]\nport = 8300\n', "utf-8")
            if local is not None:
                (racine / "config.local.toml").write_text(local, "utf-8")
            return load_config(racine)

    def test_sans_config_locale_aucune_origine(self):
        self.assertNotIn("allowed_origins", self.charger(None)["server"])

    def test_liste_locale_fusionnee(self):
        cfg = self.charger(f'[server]\nallowed_origins = ["{TUNNEL}", 42]\n')
        self.assertEqual(cfg["server"]["allowed_origins"], [TUNNEL])

    def test_chaine_locale_acceptee(self):
        cfg = self.charger(f'[server]\nallowed_origins = "{TUNNEL}"\n')
        self.assertEqual(cfg["server"]["allowed_origins"], [TUNNEL])


if __name__ == "__main__":
    unittest.main()
