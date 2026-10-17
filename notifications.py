"""notifications.py — notifications poussées (Web Push) vers le cell de Charles quand une décision l'attend.

v1.0 (2026-10-16, claude) : piste 7 acceptée par Charles. Chiffrement aes128gcm (RFC 8291) et signature VAPID
(RFC 8292) avec `cryptography` et `jwt`, déjà installés : aucune dépendance ajoutée. La clé VAPID et les
abonnements vivent dans data/ (local, hors git, fichier de clé en 0600). Le contenu est chiffré de bout en bout :
le service de push (Google pour Chrome) achemine un bloc qu'il ne peut pas lire.
"""
import base64
import json
import logging
import os
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

import jwt
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

log = logging.getLogger(__name__)

# Seuls les vrais services de push des navigateurs sont appelés (jamais une adresse fournie au hasard : pas de SSRF).
SERVICES = ("fcm.googleapis.com", "android.googleapis.com", "updates.push.services.mozilla.com",
            ".push.apple.com", ".notify.windows.com")
SUJET = "https://github.com/Groupe-Vaultia/agentchattr"  # contact VAPID public, sans adresse personnelle
TAILLE_ENREG = 4096


def b64u(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def d64u(s: str) -> bytes:
    s = str(s or "")
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def service_permis(endpoint: str) -> bool:
    u = urlparse(str(endpoint or ""))
    hote = (u.hostname or "").lower()
    return u.scheme == "https" and any(hote == s or (s.startswith(".") and hote.endswith(s)) for s in SERVICES)


def _hkdf(sel: bytes, info: bytes, longueur: int, ikm: bytes) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=longueur, salt=sel, info=info).derive(ikm)


def chiffrer(charge: bytes, p256dh: str, auth: str, sel: bytes | None = None,
             cle_ephemere: ec.EllipticCurvePrivateKey | None = None) -> bytes:
    """RFC 8291 : un seul enregistrement aes128gcm. Rend en-tête (sel, rs, clé publique éphémère) + chiffré."""
    ua_pub = d64u(p256dh)
    secret = d64u(auth)
    if len(ua_pub) != 65 or len(secret) != 16:
        raise ValueError("clés d'abonnement invalides")
    if len(charge) > TAILLE_ENREG - 17 - 86:
        raise ValueError("charge trop longue")
    sel = sel or os.urandom(16)
    cle_ephemere = cle_ephemere or ec.generate_private_key(ec.SECP256R1())
    as_pub = cle_ephemere.public_key().public_bytes(serialization.Encoding.X962,
                                                     serialization.PublicFormat.UncompressedPoint)
    partage = cle_ephemere.exchange(ec.ECDH(), ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), ua_pub))
    ikm = _hkdf(secret, b"WebPush: info\x00" + ua_pub + as_pub, 32, partage)
    cek = _hkdf(sel, b"Content-Encoding: aes128gcm\x00", 16, ikm)
    nonce = _hkdf(sel, b"Content-Encoding: nonce\x00", 12, ikm)
    chiffre = AESGCM(cek).encrypt(nonce, charge + b"\x02", None)  # \x02 : délimiteur du dernier enregistrement
    return sel + TAILLE_ENREG.to_bytes(4, "big") + bytes([len(as_pub)]) + as_pub + chiffre


class Notifications:
    def __init__(self, data_dir: str | Path):
        self._dir = Path(data_dir)
        self._fichier_cle = self._dir / "vapid.json"
        self._fichier_abos = self._dir / "push_abonnements.json"
        self._lock = threading.Lock()
        self._cle: ec.EllipticCurvePrivateKey | None = None
        self._derniers: dict[str, float] = {}  # étiquette -> heure du dernier envoi (anti-rafale)

    # ---- clé VAPID (créée au premier usage, jamais journalisée) ----
    def _cle_privee(self) -> ec.EllipticCurvePrivateKey:
        with self._lock:
            if self._cle is None:
                if self._fichier_cle.exists():
                    pem = json.loads(self._fichier_cle.read_text("utf-8"))["privee_pem"].encode()
                    self._cle = serialization.load_pem_private_key(pem, None)
                else:
                    self._cle = ec.generate_private_key(ec.SECP256R1())
                    pem = self._cle.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                                  serialization.NoEncryption()).decode()
                    self._dir.mkdir(parents=True, exist_ok=True)
                    tmp = self._fichier_cle.with_suffix(".tmp")
                    tmp.write_text(json.dumps({"privee_pem": pem}), "utf-8")
                    os.chmod(tmp, 0o600)
                    tmp.replace(self._fichier_cle)
            return self._cle

    def cle_publique(self) -> str:
        pub = self._cle_privee().public_key().public_bytes(serialization.Encoding.X962,
                                                           serialization.PublicFormat.UncompressedPoint)
        return b64u(pub)

    # ---- abonnements (un par appareil) ----
    def abonnements(self) -> list[dict]:
        with self._lock:
            try:
                return json.loads(self._fichier_abos.read_text("utf-8"))
            except (FileNotFoundError, ValueError):
                return []

    def _ecrire(self, abos: list[dict]) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        tmp = self._fichier_abos.with_suffix(".tmp")
        tmp.write_text(json.dumps(abos, ensure_ascii=False), "utf-8")
        os.chmod(tmp, 0o600)
        tmp.replace(self._fichier_abos)

    def abonner(self, abo: dict) -> str:
        """Rend '' si l'abonnement est retenu, sinon la raison du refus."""
        if not isinstance(abo, dict):
            return "abonnement attendu"
        endpoint = str(abo.get("endpoint") or "")
        cles = abo.get("keys") or {}
        if not service_permis(endpoint):
            return "service de push inconnu"
        try:
            if len(d64u(cles.get("p256dh"))) != 65 or len(d64u(cles.get("auth"))) != 16:
                return "clés d'abonnement invalides"
        except (ValueError, TypeError):
            return "clés d'abonnement invalides"
        propre = {"endpoint": endpoint, "keys": {"p256dh": str(cles["p256dh"]), "auth": str(cles["auth"])},
                  "depuis": time.time()}
        abos = [a for a in self.abonnements() if a.get("endpoint") != endpoint] + [propre]
        with self._lock:
            self._ecrire(abos[-10:])  # quelques appareils au plus
        return ""

    def desabonner(self, endpoint: str) -> None:
        abos = [a for a in self.abonnements() if a.get("endpoint") != endpoint]
        with self._lock:
            self._ecrire(abos)

    # ---- envoi ----
    def _envoyer_un(self, abo: dict, charge: bytes) -> int:
        endpoint = abo["endpoint"]
        if not service_permis(endpoint):
            return 0
        u = urlparse(endpoint)
        jeton = jwt.encode({"aud": f"{u.scheme}://{u.netloc}", "exp": int(time.time()) + 12 * 3600, "sub": SUJET},
                           self._cle_privee(), algorithm="ES256")
        corps = chiffrer(charge, abo["keys"]["p256dh"], abo["keys"]["auth"])
        req = urllib.request.Request(endpoint, data=corps, method="POST", headers={
            "Authorization": f"vapid t={jeton}, k={self.cle_publique()}",
            "Content-Encoding": "aes128gcm", "Content-Type": "application/octet-stream",
            "TTL": "86400", "Urgency": "high"})
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                return r.status
        except urllib.error.HTTPError as e:
            return e.code

    def envoyer(self, titre: str, corps: str, url: str = "/atelier", etiquette: str = "atelier",
                intervalle: float = 10.0) -> int:
        """Envoie à chaque appareil abonné ; rend le nombre d'envois acceptés. Un abonnement expiré (404/410)
        est retiré. Une même étiquette n'est pas renvoyée plus d'une fois par `intervalle` secondes."""
        maintenant = time.time()
        if maintenant - self._derniers.get(etiquette, 0) < intervalle:
            return 0
        self._derniers[etiquette] = maintenant
        charge = json.dumps({"titre": titre[:120], "corps": corps[:300], "url": url, "etiquette": etiquette[:60]},
                            ensure_ascii=False).encode()
        ok, morts = 0, []
        for abo in self.abonnements():
            try:
                code = self._envoyer_un(abo, charge)
            except Exception:
                log.exception("notification : envoi impossible")
                continue
            if code in (404, 410):
                morts.append(abo.get("endpoint"))
            elif 200 <= code < 300:
                ok += 1
            else:
                log.warning("notification : le service de push a répondu %s", code)
        for m in morts:
            self.desabonner(m)
        return ok

    def envoyer_en_fond(self, *args, **kwargs) -> None:
        """Hors de la boucle du serveur : un service de push lent ne doit jamais ralentir la salle."""
        threading.Thread(target=self.envoyer, args=args, kwargs=kwargs, daemon=True).start()
