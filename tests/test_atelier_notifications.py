"""Atelier v3 : notifications poussées (Web Push) et flux en direct de l'atelier.

v1.0 (2026-10-16, claude) : chiffrement RFC 8291 vérifié par déchiffrement, signature VAPID vérifiée par la clé
publique, services de push permis, abonnements, anti-rafale, une seule notification par attente, flux SSE.
Aucun appel réseau : l'envoi vers le service de push est simulé.
"""

import asyncio
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import app
import notifications as N


def _navigateur():
    """Clés d'un abonnement de navigateur : (clé privée, p256dh, auth)."""
    cle = ec.generate_private_key(ec.SECP256R1())
    pub = cle.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    return cle, N.b64u(pub), N.b64u(os.urandom(16))


def _dechiffrer(corps: bytes, cle_ua, p256dh: str, auth: str) -> bytes:
    """Côté navigateur (RFC 8291) : relit l'en-tête aes128gcm et déchiffre."""
    sel, rs, idlen = corps[:16], int.from_bytes(corps[16:20], "big"), corps[20]
    as_pub = corps[21:21 + idlen]
    chiffre = corps[21 + idlen:]
    assert rs == 4096
    partage = cle_ua.exchange(ec.ECDH(), ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), as_pub))
    ikm = N._hkdf(N.d64u(auth), b"WebPush: info\x00" + N.d64u(p256dh) + as_pub, 32, partage)
    cek = N._hkdf(sel, b"Content-Encoding: aes128gcm\x00", 16, ikm)
    nonce = N._hkdf(sel, b"Content-Encoding: nonce\x00", 12, ikm)
    clair = AESGCM(cek).decrypt(nonce, chiffre, None)
    assert clair.endswith(b"\x02")
    return clair[:-1]


class ChiffrementTests(unittest.TestCase):
    def test_le_navigateur_relit_ce_qui_est_chiffre(self):
        cle, p256dh, auth = _navigateur()
        charge = json.dumps({"titre": "Une décision t'attend", "corps": "Style : silhouette"}).encode()
        self.assertEqual(_dechiffrer(N.chiffrer(charge, p256dh, auth), cle, p256dh, auth), charge)

    def test_vecteur_officiel_rfc_8291(self):
        """RFC 8291 §5 : mêmes clés, même sel → exactement le même message chiffré que la norme."""
        cle = ec.derive_private_key(int.from_bytes(N.d64u("yfWPiYE-n46HLnH0KqZOF1fJJU3MYrct3AELtAQ-oRw"), "big"),
                                    ec.SECP256R1())
        corps = N.chiffrer(b"When I grow up, I want to be a watermelon",
                           "BCVxsr7N_eNgVRqvHtD0zTZsEc6-VV-JvLexhqUzORcxaOzi6-AYWXvTBHm4bjyPjs7Vd8pZGH6SRpkNtoIAiw4",
                           "BTBZMqHH6r4Tts7J_aSIgg", sel=N.d64u("DGv6ra1nlYgDCS1FRnbzlw"), cle_ephemere=cle)
        self.assertEqual(N.b64u(corps),
                         "DGv6ra1nlYgDCS1FRnbzlwAAEABBBP4z9KsN6nGRTbVYI_c7VJSPQTBtkgcy27mlmlMoZIIgDll6e3vCYLocInmYWAmS6Tlz"
                         "AC8wEqKK6PBru3jl7A_yl95bQpu6cVPTpK4Mqgkf1CXztLVBSt2Ks3oZwbuwXPXLWyouBWLVWGNWQexSgSxsj_Qulcy4a-fN")

    def test_cles_invalides_et_charge_trop_longue_refusees(self):
        _, p256dh, auth = _navigateur()
        with self.assertRaises(ValueError):
            N.chiffrer(b"x", "abc", auth)
        with self.assertRaises(ValueError):
            N.chiffrer(b"x" * 5000, p256dh, auth)

    def test_seuls_les_vrais_services_de_push_sont_appeles(self):
        self.assertTrue(N.service_permis("https://fcm.googleapis.com/fcm/send/abc"))
        self.assertTrue(N.service_permis("https://web.push.apple.com/xyz"))
        self.assertFalse(N.service_permis("http://fcm.googleapis.com/fcm/send/abc"))
        self.assertFalse(N.service_permis("https://fcm.googleapis.com.exemple.invalid/x"))
        self.assertFalse(N.service_permis("https://127.0.0.1:8300/api/v2/projects"))


class AbonnementsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.n = N.Notifications(self.tmp.name)
        _, self.p256dh, self.auth = _navigateur()
        self.abo = {"endpoint": "https://fcm.googleapis.com/fcm/send/a1", "keys": {"p256dh": self.p256dh, "auth": self.auth}}

    def test_cle_vapid_stable_et_privee(self):
        pub = self.n.cle_publique()
        self.assertEqual(N.Notifications(self.tmp.name).cle_publique(), pub)
        self.assertEqual(len(N.d64u(pub)), 65)
        self.assertEqual(os.stat(Path(self.tmp.name) / "vapid.json").st_mode & 0o777, 0o600)

    def test_abonnement_valide_garde_une_fois(self):
        self.assertEqual(self.n.abonner(self.abo), "")
        self.assertEqual(self.n.abonner(self.abo), "")
        self.assertEqual(len(self.n.abonnements()), 1)
        self.assertEqual(os.stat(Path(self.tmp.name) / "push_abonnements.json").st_mode & 0o777, 0o600)
        self.assertIn("inconnu", self.n.abonner({**self.abo, "endpoint": "https://exemple.invalid/x"}))
        self.assertIn("invalides", self.n.abonner({**self.abo, "keys": {"p256dh": "x", "auth": self.auth}}))

    def test_envoi_signe_vapid_et_abonnement_expire_retire(self):
        self.n.abonner(self.abo)
        vu = {}

        class Rep:
            status = 201
            def __enter__(self): return self
            def __exit__(self, *a): return False

        def faux_urlopen(req, timeout=0):
            vu["auth"] = req.get_header("Authorization")
            vu["encodage"] = req.get_header("Content-encoding")
            return Rep()

        with mock.patch.object(N.urllib.request, "urlopen", faux_urlopen):
            self.assertEqual(self.n.envoyer("t", "c", etiquette="e1"), 1)
        jeton = vu["auth"].split("t=")[1].split(",")[0]
        cle_pub = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), N.d64u(self.n.cle_publique()))
        claims = jwt.decode(jeton, cle_pub, algorithms=["ES256"], audience="https://fcm.googleapis.com")
        self.assertEqual(claims["sub"], N.SUJET)
        self.assertEqual(vu["encodage"], "aes128gcm")
        # anti-rafale : même étiquette tout de suite = rien
        with mock.patch.object(N.urllib.request, "urlopen", faux_urlopen):
            self.assertEqual(self.n.envoyer("t", "c", etiquette="e1"), 0)
        # abonnement expiré chez le service (410) : retiré
        with mock.patch.object(self.n, "_envoyer_un", return_value=410):
            self.assertEqual(self.n.envoyer("t", "c", etiquette="e2"), 0)
        self.assertEqual(self.n.abonnements(), [])


class DeclencheursTests(unittest.TestCase):
    def setUp(self):
        self.envois = []
        fake = mock.Mock()
        fake.envoyer_en_fond.side_effect = lambda *a, **k: self.envois.append((a, k))
        for nom, val in (("notifs", fake), ("_attente_notifiee", set())):
            p = mock.patch.object(app, nom, val)
            p.start()
            self.addCleanup(p.stop)

    def test_une_seule_notification_par_attente(self):
        t = {"type": "tache", "id": 22, "projet_id": "quad", "titre": "Style", "etat": "attend_charles"}
        app._notifier_attente(t)
        app._notifier_attente(t)                      # même attente : pas de doublon
        self.assertEqual(len(self.envois), 1)
        self.assertEqual(self.envois[0][1]["url"], "/atelier#/p/quad/taches/22")
        app._notifier_attente({**t, "etat": "en_cours"})
        app._notifier_attente(t)                      # nouvelle attente : nouvelle notification
        self.assertEqual(len(self.envois), 2)
        app._notifier_attente({"job_id": 3, "message": {}})  # autre changement : ignoré
        self.assertEqual(len(self.envois), 2)


class FluxTests(unittest.TestCase):
    def test_les_messages_et_etats_vont_au_flux_pas_le_reste(self):
        q = asyncio.Queue(maxsize=10)
        with mock.patch.object(app, "_flux_abonnes", {q}), mock.patch.object(app, "ws_clients", set()):
            asyncio.run(app.broadcast({"id": 1, "channel": "tache-22", "text": "salut"}))
            app._diffuser_flux(json.dumps({"type": "typing", "agent": "claude"}))
            app._diffuser_flux(json.dumps({"type": "message_update", "message": {"id": 1}}))
        recus = [json.loads(q.get_nowait())["type"] for _ in range(q.qsize())]
        self.assertEqual(recus, ["message", "message_update"])


if __name__ == "__main__":
    unittest.main()
