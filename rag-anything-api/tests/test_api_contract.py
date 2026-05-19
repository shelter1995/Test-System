from fastapi.testclient import TestClient

import app as rag_api


class FakeRegistry:
    def list_databases(self):
        return [{"id": "商务彩铃", "name": "商务彩铃", "status": "active", "engine": "raganything", "documents": []}]

    def get_database(self, db_id):
        if db_id == "商务彩铃":
            return {"id": "商务彩铃", "name": "商务彩铃", "status": "active", "engine": "raganything", "documents": []}
        return None


class FakeService:
    def __init__(self):
        self.registry = FakeRegistry()

    async def query(self, database_id, query, mode="hybrid", n_results=10):
        return {
            "query": query,
            "database": database_id,
            "results": [
                {
                    "text": "商务彩铃资费为10元/月/线起",
                    "metadata": {"source": "raganything", "database": database_id, "mode": mode},
                    "score": 1.0,
                }
            ],
            "total_found": 1,
        }

    async def query_all(self, query, mode="hybrid", n_results=10):
        return {
            "query": query,
            "results": [
                {
                    "text": "商务彩铃资费为10元/月/线起",
                    "metadata": {"source": "raganything", "database": "商务彩铃", "mode": mode},
                    "score": 1.0,
                }
            ],
            "total_found": 1,
        }

    async def generate_answer(self, prompt):
        assert "只能基于【知识库资料】回答" in prompt
        return "商务彩铃基础版资费为 10 元/月/线。依据：资费说明中明确写明基础版价格。"

    async def query_context(self, database_id, query, mode="naive", max_chars=3000):
        return {
            "query": query,
            "database": database_id,
            "contexts": [
                {
                    "text": "坐椅子时建议坐前缘，保持脊柱延展，双肩自然放松。",
                    "metadata": {
                        "source": "外拍动作图解.md",
                        "database": database_id,
                        "mode": mode,
                    },
                    "score": 1.0,
                }
            ],
            "total_found": 1,
        }


class FailingAnswerService(FakeService):
    async def generate_answer(self, prompt):
        raise TimeoutError("LLM timeout")


def test_db_list_contract(monkeypatch):
    monkeypatch.setattr(rag_api, "rag_service", FakeService())
    monkeypatch.setattr(rag_api, "startup_error", None)
    client = TestClient(rag_api.app)

    response = client.get("/db/list")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["count"] == 1
    assert data["databases"][0]["id"] == "商务彩铃"


def test_ai_enhanced_search_contract(monkeypatch):
    monkeypatch.setattr(rag_api, "rag_service", FakeService())
    monkeypatch.setattr(rag_api, "startup_error", None)
    client = TestClient(rag_api.app)

    response = client.post(
        "/ai_enhanced_search",
        json={"query": "资费是多少", "n_results": 3, "database": "商务彩铃"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["query"] == "资费是多少"
    assert data["results"][0]["metadata"]["source"] == "raganything"
    assert "10元" in data["results"][0]["text"]


def test_kb_chat_contract(monkeypatch):
    monkeypatch.setattr(rag_api, "rag_service", FakeService())
    monkeypatch.setattr(rag_api, "startup_error", None)
    client = TestClient(rag_api.app)

    response = client.post(
        "/kb/chat",
        json={
            "query": "坐椅子时如何摆拍照姿势",
            "database": "商务彩铃",
            "history": [{"q": "先前问题", "a": "先前回答"}],
            "n_results": 3,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["query"] == "坐椅子时如何摆拍照姿势"
    assert data["database"] == "商务彩铃"
    assert "answer" in data and isinstance(data["answer"], str)
    assert "sources" in data and isinstance(data["sources"], list)
    assert "10 元/月/线" in data["answer"]
    assert data["answer"] != data["sources"][0]["snippet"]
    assert data["fallback"] in (None, "local_text")


def test_kb_chat_falls_back_to_context_summary_when_answer_generation_fails(monkeypatch):
    monkeypatch.setattr(rag_api, "rag_service", FailingAnswerService())
    monkeypatch.setattr(rag_api, "startup_error", None)
    client = TestClient(rag_api.app)

    response = client.post(
        "/kb/chat",
        json={"query": "坐椅子时如何摆拍照姿势", "database": "商务彩铃"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["fallback"] == "answer_generation_failed"
    assert "答案生成服务暂时不可用" in data["answer"]
    assert "坐前缘" in data["answer"]
