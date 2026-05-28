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


def test_delete_session_removes_saved_record(tmp_path, monkeypatch):
    import json
    import tutor_config

    monkeypatch.setattr(tutor_config, "SESSIONS_DIR", str(tmp_path))
    session_file = tmp_path / "session-delete-me.json"
    session_file.write_text(
        json.dumps({"session_id": "session-delete-me", "scenario": {"name": "测试场景"}}),
        encoding="utf-8",
    )

    client = TestClient(tutor_backend.app)
    response = client.delete("/session/session-delete-me")

    assert response.status_code == 200
    assert response.json()["status"] == "success"
    assert not session_file.exists()


def test_export_session_pdf_returns_pdf(tmp_path, monkeypatch):
    import json
    import tutor_config

    monkeypatch.setattr(tutor_config, "SESSIONS_DIR", str(tmp_path))
    session_file = tmp_path / "session-export.json"
    session_file.write_text(
        json.dumps(
            {
                "session_id": "session-export",
                "client_unit": "测试客户",
                "product": "测试产品",
                "scenario": {"name": "价格敏感型客户"},
                "round": 1,
                "status": "completed",
                "messages": [
                    {"role": "user", "content": "您好，介绍一下产品。"},
                    {"role": "ai", "content": "请说明价格优势。"},
                ],
                "report": {
                    "total_score": 86,
                    "rating_text": "优秀",
                    "highlights": ["开场清晰"],
                    "improvements": ["补充案例"],
                    "suggestions": ["明确下一步"],
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    client = TestClient(tutor_backend.app)
    response = client.get("/session/session-export/export.pdf")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert "filename*=UTF-8''" in response.headers["content-disposition"]
    assert "%E6%B5%8B%E8%AF%95%E5%AE%A2%E6%88%B7" in response.headers["content-disposition"]
    assert "%E6%B5%8B%E8%AF%95%E4%BA%A7%E5%93%81" in response.headers["content-disposition"]
    assert response.content.startswith(b"%PDF")


def test_pdf_export_uses_wrapped_paragraphs_for_dimension_feedback():
    import inspect

    source = inspect.getsource(tutor_backend._build_session_pdf)

    assert 'wordWrap="CJK"' in source
    assert 'Paragraph(text(value.get("feedback", "")), styles["table_cell"])' in source
