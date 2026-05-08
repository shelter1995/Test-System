from fastapi.testclient import TestClient

import app as rag_api


class FakeRegistry:
    def list_databases(self):
        return [{"id": "商务彩铃", "name": "商务彩铃", "status": "active", "documents": []}]

    def get_database(self, db_id):
        if db_id == "商务彩铃":
            return {"id": "商务彩铃", "name": "商务彩铃", "status": "active", "documents": []}
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
