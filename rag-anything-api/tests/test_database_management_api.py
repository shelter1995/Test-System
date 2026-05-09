"""
扩展 RAG 知识库注册表的测试：
- register_database 保存 description/working_dir/output_dir
- update_database 更新 name/description/status
- list_documents 返回指定知识库的文件列表
"""

from pathlib import Path

import pytest

from database_registry import DatabaseRegistry


# ── register_database: description, working_dir, output_dir ──────────────


class TestRegisterDatabaseMetadata:
    """register_database 应保存 description、working_dir、output_dir。"""

    def test_register_with_description(self, tmp_path: Path):
        registry = DatabaseRegistry(tmp_path / "databases.json")
        result = registry.register_database(
            "test-db", description="A test knowledge base"
        )
        assert result["description"] == "A test knowledge base"
        # 持久化后也能读到
        loaded = registry.get_database("test-db")
        assert loaded is not None
        assert loaded["description"] == "A test knowledge base"

    def test_register_with_working_dir_and_output_dir(self, tmp_path: Path):
        registry = DatabaseRegistry(tmp_path / "databases.json")
        result = registry.register_database(
            "test-db",
            working_dir="/data/work",
            output_dir="/data/output",
        )
        assert result["working_dir"] == "/data/work"
        assert result["output_dir"] == "/data/output"
        loaded = registry.get_database("test-db")
        assert loaded is not None
        assert loaded["working_dir"] == "/data/work"
        assert loaded["output_dir"] == "/data/output"

    def test_update_existing_preserves_description(self, tmp_path: Path):
        """对已有库再次 register，description 应保留（如果未传新值）。"""
        registry = DatabaseRegistry(tmp_path / "databases.json")
        registry.register_database("test-db", description="Original")
        result = registry.register_database("test-db")
        assert result["description"] == "Original"

    def test_update_existing_overwrites_description(self, tmp_path: Path):
        """对已有库再次 register，传新 description 应覆盖。"""
        registry = DatabaseRegistry(tmp_path / "databases.json")
        registry.register_database("test-db", description="Original")
        result = registry.register_database("test-db", description="Updated")
        assert result["description"] == "Updated"


# ── update_database ──────────────────────────────────────────────────────


class TestUpdateDatabase:
    """update_database 应能更新 name、description、status。"""

    def test_update_name(self, tmp_path: Path):
        registry = DatabaseRegistry(tmp_path / "databases.json")
        registry.register_database("test-db", name="Original")
        result = registry.update_database("test-db", name="Renamed")
        assert result["name"] == "Renamed"
        loaded = registry.get_database("test-db")
        assert loaded is not None
        assert loaded["name"] == "Renamed"

    def test_update_description(self, tmp_path: Path):
        registry = DatabaseRegistry(tmp_path / "databases.json")
        registry.register_database("test-db", description="Old desc")
        result = registry.update_database("test-db", description="New desc")
        assert result["description"] == "New desc"

    def test_update_status(self, tmp_path: Path):
        registry = DatabaseRegistry(tmp_path / "databases.json")
        registry.register_database("test-db")
        result = registry.update_database("test-db", status="archived")
        assert result["status"] == "archived"

    def test_update_multiple_fields(self, tmp_path: Path):
        registry = DatabaseRegistry(tmp_path / "databases.json")
        registry.register_database("test-db")
        result = registry.update_database(
            "test-db", name="New Name", description="New Desc", status="paused"
        )
        assert result["name"] == "New Name"
        assert result["description"] == "New Desc"
        assert result["status"] == "paused"

    def test_update_nonexistent_raises_key_error(self, tmp_path: Path):
        registry = DatabaseRegistry(tmp_path / "databases.json")
        with pytest.raises(KeyError):
            registry.update_database("nonexistent", name="X")

    def test_update_persists_changes(self, tmp_path: Path):
        """更新后重新加载也能读到。"""
        path = tmp_path / "databases.json"
        registry = DatabaseRegistry(path)
        registry.register_database("test-db")
        registry.update_database("test-db", name="Persisted")

        registry2 = DatabaseRegistry(path)
        loaded = registry2.get_database("test-db")
        assert loaded is not None
        assert loaded["name"] == "Persisted"


# ── list_documents ───────────────────────────────────────────────────────


class TestListDocuments:
    """list_documents 应返回指定知识库的文件列表。"""

    def test_list_documents_empty(self, tmp_path: Path):
        registry = DatabaseRegistry(tmp_path / "databases.json")
        registry.register_database("test-db")
        docs = registry.list_documents("test-db")
        assert docs == []

    def test_list_documents_with_registered_docs(self, tmp_path: Path):
        registry = DatabaseRegistry(tmp_path / "databases.json")
        registry.register_database("test-db")
        registry.register_document(
            "test-db",
            file_name="a.pdf",
            file_path="/data/a.pdf",
            sha256="aaa",
        )
        registry.register_document(
            "test-db",
            file_name="b.png",
            file_path="/data/b.png",
            sha256="bbb",
        )
        docs = registry.list_documents("test-db")
        assert len(docs) == 2
        names = {d["file_name"] for d in docs}
        assert names == {"a.pdf", "b.png"}

    def test_list_documents_nonexistent_raises_key_error(self, tmp_path: Path):
        registry = DatabaseRegistry(tmp_path / "databases.json")
        with pytest.raises(KeyError):
            registry.list_documents("nonexistent")
