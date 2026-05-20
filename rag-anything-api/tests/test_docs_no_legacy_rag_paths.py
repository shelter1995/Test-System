from pathlib import Path


def test_user_facing_docs_do_not_recommend_legacy_rag_storage_or_endpoints():
    root = Path(__file__).resolve().parents[2]
    docs = [
        root / "rag_database_guide.md",
        root / "使用说明.md",
        root / "README.md",
        root / "SETUP.md",
        root / "部署说明.md",
    ]
    forbidden = [
        "chroma.sqlite3",
        "chromadb",
        "Chroma",
        "storage\\\\lightrag\\\\{数据库ID}",
        "storage/lightrag/{数据库ID}",
        "/ingest/file",
        "/ingest/folder",
        "旧图片处理器",
        "旧向量库",
    ]
    offenders = []
    for doc in docs:
        assert doc.exists(), f"Document listed in legacy-path check is missing: {doc}"
        text = doc.read_text(encoding="utf-8")
        for pattern in forbidden:
            if pattern in text:
                offenders.append(f"{doc.name}: {pattern}")

    assert offenders == []
