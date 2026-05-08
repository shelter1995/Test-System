from pathlib import Path

from database_registry import DatabaseRegistry
from raganything_service import RAGAnythingService


class FakeRAG:
    def __init__(self, name):
        self.name = name


def test_get_rag_evicts_least_recently_used_instance(tmp_path: Path):
    registry = DatabaseRegistry(tmp_path / "databases.json")
    for db_id in ["A", "B", "C"]:
        registry.register_database(db_id)

    created = []

    def factory(db_id, _wd):
        rag = FakeRAG(db_id)
        created.append(rag)
        return rag

    service = RAGAnythingService(
        storage_root=tmp_path / "raganything",
        output_root=tmp_path / "output",
        registry=registry,
        rag_factory=factory,
        max_instances=2,
    )

    service.get_rag("A")
    service.get_rag("B")
    service.get_rag("A")
    service.get_rag("C")

    assert list(service._instances.keys()) == ["A", "C"]
    assert [rag.name for rag in created] == ["A", "B", "C"]


def test_unload_rag_removes_cached_instance(tmp_path: Path):
    registry = DatabaseRegistry(tmp_path / "databases.json")
    registry.register_database("商务彩铃")
    service = RAGAnythingService(
        storage_root=tmp_path / "raganything",
        output_root=tmp_path / "output",
        registry=registry,
        rag_factory=lambda db_id, _wd: FakeRAG(db_id),
        max_instances=2,
    )

    service.get_rag("商务彩铃")
    removed = service.unload_rag("商务彩铃")

    assert removed is True
    assert "商务彩铃" not in service._instances
    assert service.unload_rag("商务彩铃") is False
