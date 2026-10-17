"""Atelier v3 : Charles écrit dans la conversation d'une tâche depuis l'atelier (POST /api/v2/messages).

v1.0 (2026-10-16, claude) : expéditeur imposé, canal connu, étiquette de tâche reprise du canal,
pièces jointes limitées aux dépôts /uploads/.
v1.1 (2026-10-16, claude) : appelle la route directement au lieu d'un TestClient. Démarrer l'application
partagée empêchait test_livrables_auto (qui passe après) d'y ajouter son intergiciel.
"""

import asyncio
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from starlette.requests import Request

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import app
import projects
from jobs import JobStore
from store import MessageStore


class AtelierConversationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        projects.configurer(root / "projects.json")
        projects.creer("Synthetic Alpha")
        self.store = MessageStore(str(root / "messages.jsonl"))
        self.jobs = JobStore(str(root / "jobs.json"))
        self.task, err = self.jobs.create_tache("synthetic-alpha", "Task", "prototype", "claude", "user",
                                                equipe=[{"agent": "claude", "role": "producteur"}])
        self.assertEqual(err, "")
        self.canal = f"tache-{self.task['id']}"
        settings = dict(app.room_settings)
        settings["channels"] = ["general", self.canal]
        settings["username"] = "user"
        for name, value in (("store", self.store), ("jobs", self.jobs), ("room_settings", settings)):
            patcher = mock.patch.object(app, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def poster(self, corps):
        """POST /api/v2/messages sans démarrer l'application : rend (code, json)."""
        donnees = json.dumps(corps).encode()

        async def recevoir():
            return {"type": "http.request", "body": donnees, "more_body": False}

        requete = Request({"type": "http", "method": "POST", "path": "/api/v2/messages",
                           "headers": [(b"content-type", b"application/json")]}, recevoir)
        reponse = asyncio.run(app.ecrire_message(requete))
        return reponse.status_code, json.loads(reponse.body)

    def test_message_goes_to_task_channel_with_its_tag(self):
        code, msg = self.poster({"channel": self.canal, "text": "@claude on avance ?"})
        self.assertEqual(code, 200)
        self.assertEqual(msg["sender"], "user")
        self.assertEqual(msg["channel"], self.canal)
        self.assertEqual(msg["tache_id"], self.task["id"])
        self.assertEqual(msg["projet_id"], "synthetic-alpha")
        self.assertEqual(self.store.get_recent(5, channel=self.canal)[-1]["text"], "@claude on avance ?")

    def test_sender_cannot_be_chosen_by_the_page(self):
        code, msg = self.poster({"channel": self.canal, "text": "salut", "sender": "codex"})
        self.assertEqual(code, 200)
        self.assertEqual(msg["sender"], "user")

    def test_unknown_channel_and_empty_text_are_refused(self):
        self.assertEqual(self.poster({"channel": "inconnu", "text": "x"})[0], 404)
        self.assertEqual(self.poster({"channel": self.canal, "text": "  "})[0], 400)
        self.assertEqual(self.poster({"channel": self.canal, "text": "x", "tache_id": 999})[0], 422)

    def test_only_uploaded_files_are_attached(self):
        code, msg = self.poster({"channel": self.canal, "text": "photo", "attachments": [
            {"name": "a.jpg", "url": "/uploads/a.jpg"},
            {"name": "b.jpg", "url": "https://exemple.invalid/b.jpg"},
            {"name": "c.jpg", "url": "/uploads/../data/session_token"},
        ]})
        self.assertEqual(code, 200)
        self.assertEqual(msg["attachments"], [{"name": "a.jpg", "url": "/uploads/a.jpg"}])


if __name__ == "__main__":
    unittest.main()
