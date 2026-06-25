from fastapi.testclient import TestClient

import app as rag_api
from database_registry import DatabaseRegistry


class FakeRegistry:
    def __init__(self, registry_file):
        self.registry_file = registry_file
        self.seeded = []

    def list_databases(self):
        return [{"id": "商务彩铃", "name": "商务彩铃", "status": "active", "documents": []}]

    def get_database(self, db_id):
        return {"id": db_id, "name": db_id, "status": "active", "documents": []}

    def register_database(self, database_id, name=None, working_dir=None, output_dir=None):
        item = {
            "id": database_id,
            "name": name or database_id,
            "status": "active",
            "documents": [],
            "working_dir": working_dir or "",
            "output_dir": output_dir or "",
        }
        self.seeded.append(item)
        return item


class FakeService:
    def __init__(self, storage_root, output_root, registry, settings_provider=None):
        self.storage_root = storage_root
        self.output_root = output_root
        self.registry = registry
        self.settings_provider = settings_provider


def test_lifespan_initializes_registry_and_service(monkeypatch, tmp_path):
    monkeypatch.setattr(rag_api.config, "DATABASE_REGISTRY_FILE", tmp_path / "databases.json")
    monkeypatch.setattr(rag_api.config, "RAGANYTHING_STORAGE_ROOT", tmp_path / "raganything")
    monkeypatch.setattr(rag_api.config, "RAGANYTHING_OUTPUT_ROOT", tmp_path / "output")
    monkeypatch.setattr(rag_api.config, "DEFAULT_DATABASE_IDS", ["商务彩铃"])
    monkeypatch.setattr(rag_api, "DatabaseRegistry", FakeRegistry)
    monkeypatch.setattr(rag_api, "RAGAnythingService", FakeService)

    rag_api.rag_service = None
    rag_api.registry = None
    rag_api.startup_error = "previous error"

    with TestClient(rag_api.app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["engine"] == "ready"
    assert rag_api.startup_error is None
    assert isinstance(rag_api.rag_service, FakeService)
    assert rag_api.rag_service.settings_provider is rag_api._runtime_model_settings


def test_fresh_registry_does_not_seed_legacy_default_database(monkeypatch, tmp_path):
    registry_file = tmp_path / "storage" / "databases.json"
    monkeypatch.setattr(rag_api.config, "DATABASE_REGISTRY_FILE", registry_file)
    monkeypatch.setattr(rag_api.config, "LEGACY_LIGHTRAG_DIR", tmp_path / "storage" / "lightrag")
    monkeypatch.setattr(rag_api.config, "RAGANYTHING_STORAGE_ROOT", tmp_path / "storage" / "raganything")
    monkeypatch.setattr(rag_api.config, "RAGANYTHING_OUTPUT_ROOT", tmp_path / "output")

    rag_api.registry = DatabaseRegistry(registry_file)
    rag_api._ensure_registry_seeded()

    assert rag_api.registry.list_databases() == []
