import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent))

import tutor_backend


def test_pause_evaluation_does_not_append_duplicate(monkeypatch):
    session_id = "session-test"
    tutor_backend.sessions[session_id] = {
        "session_id": session_id,
        "scenario": {"name": "测试场景", "ai_role": "客户"},
        "product": "产品",
        "database": "kb",
        "round": 1,
        "messages": [
            {"role": "user", "content": "你好"},
            {"role": "ai", "content": "我关注价格"},
        ],
        "evaluations": [
            {"round": 1, "overall_score": 75, "dimension_scores": {}, "feedback": "old", "suggestions": []}
        ],
        "status": "active",
    }
    monkeypatch.setattr(
        tutor_backend.ai_service,
        "evaluate",
        lambda *args, **kwargs: {
            "round": 1,
            "overall_score": 82,
            "dimension_scores": {},
            "feedback": "new",
            "suggestions": [],
        },
    )

    client = TestClient(tutor_backend.app)
    response = client.post("/chat", json={"session_id": session_id, "message": "", "is_pause": True})

    assert response.status_code == 200
    assert response.json()["evaluation"]["overall_score"] == 75
    assert len(tutor_backend.sessions[session_id]["evaluations"]) == 1
