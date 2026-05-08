from pathlib import Path


def test_runtime_python_paths_do_not_use_legacy_direct_rag_stacks():
    root = Path(__file__).resolve().parents[1]
    forbidden = [
        "from lightrag import LightRAG",
        "LightRAG(",
        ".ainsert(",
        "from sentence_transformers",
        "chromadb",
        "Chroma",
        "FAISS",
    ]
    offenders = []

    for path in root.glob("*.py"):
        if path.name == "raganything_service.py":
            continue
        text = path.read_text(encoding="utf-8")
        for pattern in forbidden:
            if pattern in text:
                offenders.append(f"{path.name}: {pattern}")

    assert offenders == []
