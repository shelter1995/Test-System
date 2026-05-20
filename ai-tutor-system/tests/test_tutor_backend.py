import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent))

import tutor_backend


def test_pause_evaluation_does_not_append_duplicate(monkeypatch):
    session_id = "session-test"
    original_sessions = tutor_backend.sessions.copy()
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

    try:
        client = TestClient(tutor_backend.app)
        response = client.post("/chat", json={"session_id": session_id, "message": "", "is_pause": True})

        assert response.status_code == 200
        assert response.json()["evaluation"]["overall_score"] == 75
        assert len(tutor_backend.sessions[session_id]["evaluations"]) == 1
    finally:
        tutor_backend.sessions.clear()
        tutor_backend.sessions.update(original_sessions)


def test_tutor_prompt_includes_rag_context_sources():
    from tutor_services import build_rag_context_prompt

    context = {
        "contexts": [
            {"text": "产品支持企业欢迎语。", "metadata": {"source": "product.md"}},
        ]
    }

    prompt = build_rag_context_prompt(context)

    assert "产品支持企业欢迎语" in prompt
    assert "product.md" in prompt


def test_history_list_tolerates_legacy_sessions_without_created_at(tmp_path, monkeypatch):
    import json
    import tutor_config
    from tutor_services import SessionManager

    monkeypatch.setattr(tutor_config, "SESSIONS_DIR", str(tmp_path))
    (tmp_path / "legacy.json").write_text(
        json.dumps(
            {
                "session_id": "legacy",
                "scenario": {"name": "测试场景"},
                "round": 2,
                "status": "active",
                "messages": [{"role": "user", "content": "你好"}],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    history = SessionManager.list_all()

    assert history[0]["session_id"] == "legacy"
    assert history[0]["scenario"] == "测试场景"
    assert history[0]["created_at"]
