"""
内容生成 API 测试

使用 FastAPI TestClient 测试 generation_api 路由。
Mock generation_runner 以避免实际执行脚本。
"""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

# 将 ai-tutor-system 目录加入 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from generation_api import router
from fastapi import FastAPI


def _make_app() -> FastAPI:
    """创建仅挂载 generation 路由的测试用 FastAPI 应用。"""
    app = FastAPI()
    app.include_router(router)
    return app


client = TestClient(_make_app())


# ==================== POST /generation/jobs ====================


class TestCreateJob:
    """测试创建生成作业。"""

    @patch("generation_runner.create_job", return_value="abc123def456")
    def test_returns_job_id_and_running_status(self, mock_create):
        """创建作业应返回 job_id 和 status=running。"""
        resp = client.post(
            "/generation/jobs",
            json={"database": "test_db", "client_unit": "TestCo", "product": "TestProduct"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["job_id"] == "abc123def456"
        assert data["status"] == "running"
        mock_create.assert_called_once()

    @patch("generation_runner.create_job", return_value="job001")
    def test_accepts_empty_body(self, mock_create):
        """请求体为空时应使用默认值。"""
        resp = client.post("/generation/jobs", json={})
        assert resp.status_code == 200
        data = resp.json()
        assert data["job_id"] == "job001"
        assert data["status"] == "running"


# ==================== GET /generation/jobs/{job_id} ====================


class TestGetJob:
    """测试查询作业状态。"""

    @patch(
        "generation_runner.get_job",
        return_value={
            "job_id": "abc123def456",
            "status": "completed",
            "created_at": "2026-05-09T00:00:00+00:00",
            "result": {"stdout": "done"},
            "error": None,
        },
    )
    def test_returns_job_details(self, mock_get):
        """查询存在的作业应返回完整详情。"""
        resp = client.get("/generation/jobs/abc123def456")
        assert resp.status_code == 200
        data = resp.json()
        assert data["job_id"] == "abc123def456"
        assert data["status"] == "completed"
        assert data["result"]["stdout"] == "done"

    @patch("generation_runner.get_job", return_value=None)
    def test_returns_404_for_missing_job(self, mock_get):
        """查询不存在的作业应返回 404。"""
        resp = client.get("/generation/jobs/000000000000")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    def test_returns_400_for_invalid_job_id(self):
        """格式非法的 job_id 应返回 400。"""
        resp = client.get("/generation/jobs/nonexistent")
        assert resp.status_code == 400
        assert "invalid" in resp.json()["detail"].lower()


# ==================== GET /generation/artifacts ====================


class TestListArtifacts:
    """测试列出历史产物。"""

    @patch(
        "generation_runner.list_artifacts",
        return_value=[
            {
                "name": "training_guide.md",
                "path": "training_output/training_guide.md",
                "size": 1024,
                "modified": "2026-05-09T00:00:00+00:00",
            },
            {
                "name": "solution.md",
                "path": "solution_output/solution.md",
                "size": 512,
                "modified": "2026-05-08T12:00:00+00:00",
            },
        ],
    )
    def test_returns_artifact_list(self, mock_list):
        """列出产物应返回包含 name、path、size、modified 的列表。"""
        resp = client.get("/generation/artifacts")
        assert resp.status_code == 200
        data = resp.json()
        assert "artifacts" in data
        assert len(data["artifacts"]) == 2
        assert data["artifacts"][0]["name"] == "training_guide.md"
        assert data["artifacts"][1]["name"] == "solution.md"

    @patch("generation_runner.list_artifacts", return_value=[])
    def test_returns_empty_list_when_no_artifacts(self, mock_list):
        """无产物时应返回空列表。"""
        resp = client.get("/generation/artifacts")
        assert resp.status_code == 200
        data = resp.json()
        assert data["artifacts"] == []


# ==================== GET /generation/artifacts/download ====================


class TestDownloadArtifact:
    """测试下载产物文件。"""

    def test_rejects_path_traversal(self):
        """路径穿越攻击应被拒绝（relative_to 检查返回 400）。"""
        resp = client.get("/generation/artifacts/download?path=../tutor_config.py")
        assert resp.status_code == 400

    def test_rejects_path_traversal_from_allowed_dir(self):
        """从允许目录出发的路径穿越也应被拒绝。"""
        resp = client.get(
            "/generation/artifacts/download?path=training_output/../../tutor_config.py"
        )
        assert resp.status_code == 400

    def test_rejects_non_allowed_directory(self):
        """不在允许目录中的路径应被拒绝。"""
        resp = client.get("/generation/artifacts/download?path=static/index.html")
        assert resp.status_code == 403

    def test_returns_404_for_missing_file(self):
        """不存在的文件应返回 404。"""
        resp = client.get(
            "/generation/artifacts/download?path=training_output/nonexistent.md"
        )
        assert resp.status_code == 404
