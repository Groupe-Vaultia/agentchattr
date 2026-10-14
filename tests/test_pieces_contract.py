"""Contract tests for the Parts/BOM v0.6 spec.

v0.2 (2026-10-14, codex): ajoute `par` aux écritures et couvre source javascript:, réception
négative et changement de type d'un assemblage non vide.
"""

import copy
import hashlib
import sqlite3
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import app
import projects


class PiecesContractTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.data = self.root / "data"
        self.deliverables = self.root / "deliverables"
        self.deliverables.mkdir()

        self._app_state = app.__dict__.copy()
        self._room_settings = copy.deepcopy(app.room_settings)
        self._middleware = list(app.app.user_middleware)
        self._projects_state = (projects._state, projects._FILE)
        self.addCleanup(self._restore_globals)

        # Keep the production initialization path, but don't leave its two daemon loops running in tests.
        with mock.patch.object(app, "_load_settings"), mock.patch.object(app, "_load_hats"), \
                mock.patch.object(threading.Thread, "start"):
            app.configure({
                "server": {"data_dir": str(self.data)},
                "agents": {}, "routing": {}, "images": {},
                "socle": {"racine_livrables": str(self.deliverables)},
            }, session_token="test-pieces-session")

        projects.configurer(self.root / "projects.json")
        self.project_id = projects.creer("Synthetic Parts Project")
        self.client = TestClient(app.app, headers={"x-session-token": "test-pieces-session"})
        self.addCleanup(self.client.close)

    def _restore_globals(self):
        # configure() adds runtime globals (including the future PiecesStore) and session middleware.
        for key in list(app.__dict__):
            if key not in self._app_state:
                delattr(app, key)
        for key, value in self._app_state.items():
            setattr(app, key, value)
        app.room_settings.clear()
        app.room_settings.update(self._room_settings)
        app.app.user_middleware = self._middleware
        app.app.middleware_stack = None
        projects._state, projects._FILE = self._projects_state

    def _create_piece(self, name, origine="concevoir", type_="piece"):
        response = self.client.post("/api/v2/pieces", json={
            "nom": name, "origine": origine, "type": type_, "projet_id": self.project_id,
            "par": "claude",
        })
        self.assertIn(response.status_code, (200, 201), response.text)
        data = response.json()
        piece = data.get("piece", data)
        self.assertIn("id", piece, data)
        return piece

    @staticmethod
    def _find_node(node, piece_id):
        if isinstance(node, dict):
            if str(node.get("id", node.get("piece_id", ""))) == str(piece_id):
                return node
            for value in node.values():
                found = PiecesContractTests._find_node(value, piece_id)
                if found is not None:
                    return found
        elif isinstance(node, list):
            for value in node:
                found = PiecesContractTests._find_node(value, piece_id)
                if found is not None:
                    return found
        return None

    def test_bom_rejects_a_cycle(self):
        parent = self._create_piece("Assembly", type_="assemblage")
        child = self._create_piece("Subassembly", type_="assemblage")

        forward = self.client.post("/api/v2/nomenclature", json={
            "parent_id": parent["id"], "enfant_id": child["id"], "quantite": 2,
        })
        self.assertIn(forward.status_code, (200, 201), forward.text)

        cycle = self.client.post("/api/v2/nomenclature", json={
            "parent_id": child["id"], "enfant_id": parent["id"], "quantite": 1,
        })
        self.assertEqual(cycle.status_code, 409, cycle.text)

    def test_nested_bom_reports_cumulative_quantity(self):
        root = self._create_piece("Quad", type_="assemblage")
        assembly = self._create_piece("Front suspension", type_="assemblage")
        part = self._create_piece("Bearing", origine="acheter")

        for parent_id, child_id, quantity in (
            (root["id"], assembly["id"], 2),
            (assembly["id"], part["id"], 3),
        ):
            response = self.client.post("/api/v2/nomenclature", json={
                "parent_id": parent_id, "enfant_id": child_id, "quantite": quantity,
            })
            self.assertIn(response.status_code, (200, 201), response.text)

        tree = self.client.get(f"/api/v2/pieces/{root['id']}/nomenclature")
        self.assertEqual(tree.status_code, 200, tree.text)
        bearing = self._find_node(tree.json(), part["id"])
        self.assertIsNotNone(bearing, tree.json())
        self.assertEqual(bearing.get("quantite_cumulee"), 6, bearing)

    def test_offer_without_source_is_rejected(self):
        part = self._create_piece("Bought bearing", origine="acheter")
        database = self.data / "pieces.db"
        with sqlite3.connect(database) as db:
            cursor = db.execute(
                "INSERT INTO fournisseurs (nom, site) VALUES (?, ?)",
                ("Synthetic Supplier", "https://supplier.invalid"),
            )
            supplier_id = cursor.lastrowid

        offer = {
            "fournisseur_id": supplier_id, "reference": "BRG-01", "prix": 12.5,
            "devise": "CAD", "quantite_min": 1, "date": "2026-10-14", "par": "claude",
        }
        response = self.client.post(f"/api/v2/pieces/{part['id']}/offres", json=offer)
        self.assertEqual(response.status_code, 400, response.text)

        sourced = self.client.post(f"/api/v2/pieces/{part['id']}/offres", json={
            **offer, "source": "https://supplier.invalid/products/brg-01",
        })
        self.assertIn(sourced.status_code, (200, 201), sourced.text)

    def test_revision_change_keeps_prior_revision_record_and_file(self):
        part = self._create_piece("Designed bracket")
        old_file = self.deliverables / "bracket_P01.FCStd"
        new_file = self.deliverables / "bracket_P02.FCStd"
        old_bytes, new_bytes = b"revision P01", b"revision P02"
        old_file.write_bytes(old_bytes)
        new_file.write_bytes(new_bytes)

        first = self.client.patch(f"/api/v2/pieces/{part['id']}", json={
            "revision": "P01", "fichier": old_file.name,
            "empreinte": hashlib.sha256(old_bytes).hexdigest(),
            "par": "claude",
        })
        self.assertEqual(first.status_code, 200, first.text)
        second = self.client.patch(f"/api/v2/pieces/{part['id']}", json={
            "revision": "P02", "fichier": new_file.name,
            "empreinte": hashlib.sha256(new_bytes).hexdigest(),
            "par": "claude",
        })
        self.assertEqual(second.status_code, 200, second.text)

        self.assertTrue(old_file.exists(), "publier une nouvelle révision ne doit pas supprimer l'ancien livrable")
        with sqlite3.connect(self.data / "pieces.db") as db:
            revisions = db.execute(
                "SELECT avant, apres FROM historique_pieces WHERE piece_id = ?",
                (part["id"],),
            ).fetchall()
        self.assertIn(("P01", "P02"), revisions)

    def test_javascript_offer_source_is_rejected(self):
        part = self._create_piece("Bought bushing", origine="acheter")
        response = self.client.post(f"/api/v2/pieces/{part['id']}/offres", json={
            "reference": "BUSH-01", "prix": 1.25, "devise": "CAD",
            "source": "javascript:alert(1)", "par": "claude",
        })
        self.assertEqual(response.status_code, 400, response.text)

    def test_negative_reception_is_rejected(self):
        part = self._create_piece("Received bracket")
        response = self.client.post(f"/api/v2/pieces/{part['id']}/mouvements", json={
            "quoi": "reception", "quantite": -1, "par": "claude",
        })
        self.assertEqual(response.status_code, 400, response.text)

    def test_assembly_with_children_cannot_change_to_piece(self):
        assembly = self._create_piece("Frame", type_="assemblage")
        child = self._create_piece("Rail")
        linked = self.client.post("/api/v2/nomenclature", json={
            "parent_id": assembly["id"], "enfant_id": child["id"], "quantite": 1,
        })
        self.assertIn(linked.status_code, (200, 201), linked.text)

        changed = self.client.patch(f"/api/v2/pieces/{assembly['id']}", json={
            "type": "piece", "par": "claude",
        })
        self.assertEqual(changed.status_code, 409, changed.text)


if __name__ == "__main__":
    unittest.main()
