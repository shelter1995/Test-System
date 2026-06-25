"""
内容生成 API 测试

使用 FastAPI TestClient 测试 generation_api 路由。
Mock generation_runner 以避免实际执行脚本。
"""

import sys
from pathlib import Path
from uuid import uuid4
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

# 将 ai-tutor-system 目录加入 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent))

import generation_api
from generation_api import _resolve_artifact_path, router
from fastapi import FastAPI


def _make_app() -> FastAPI:
    """创建仅挂载 generation 路由的测试用 FastAPI 应用。"""
    app = FastAPI()
    app.include_router(router)
    return app


client = TestClient(_make_app())


@pytest.fixture(autouse=True)
def isolate_runtime_path_cache(monkeypatch):
    monkeypatch.delenv("TEST_SYSTEM_GENERATION_OUTPUT_DIR", raising=False)
    generation_api.runtime_paths_module.get_runtime_paths.cache_clear()
    yield
    generation_api.runtime_paths_module.get_runtime_paths.cache_clear()


# ==================== POST /generation/jobs ====================


class TestCreateJob:
    """测试创建生成作业。"""

    @patch("generation_runner.create_job", return_value="abc123def456")
    def test_returns_job_id_and_running_status(self, mock_create):
        """创建 solution 作业应返回 job_id 和 status=running。"""
        resp = client.post(
            "/generation/jobs",
            json={
                "type": "solution",
                "database": "test_db",
                "client_unit": "TestCo",
                "decision_maker_role": "市场总监",
                "relationship_level": "良好关系",
                "pain_challenges": "宣传效果不佳",
                "pain_scenarios": "客户咨询",
                "pain_dissatisfaction": "传统方式单一",
                "decision_focus": "效果导向",
                "decision_process": "部门决策",
                "decision_timeline": "常规（1-2个月）",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["job_id"] == "abc123def456"
        assert data["status"] == "running"
        mock_create.assert_called_once()

    @patch("generation_runner.create_job", return_value="job001")
    def test_accepts_minimal_body(self, mock_create):
        """请求体仅包含必需字段 type 和 database 时应成功。"""
        resp = client.post("/generation/jobs", json={"type": "training", "database": "test_db"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["job_id"] == "job001"
        assert data["status"] == "running"

    def test_rejects_invalid_type(self):
        """无效的 type 应返回 400。"""
        resp = client.post("/generation/jobs", json={"type": "invalid_type"})
        assert resp.status_code == 400

    @patch("generation_runner.create_job", return_value="train001")
    def test_accepts_training_with_full_config(self, mock_create):
        """创建 training 作业时接受完整考试配置。"""
        resp = client.post(
            "/generation/jobs",
            json={
                "type": "training",
                "database": "test_db",
                "training_theme": "销售培训",
                "target_customer_group": "政务客户+教育客户",
                "trainee_level": "有经验人员",
                "trainee_base": "1-3年经验",
                "duration": "半天（3-4小时）",
                "training_goals": "能够销售产品",
                "focus_areas": "痛点挖掘+话术技巧",
                "exam_question_count": 20,
                "exam_question_types": ["选择题", "填空题", "简答题", "案例分析题"],
                "exam_difficulty_distribution": {"基础": 50, "进阶": 30, "挑战": 20},
                "exam_total_score": 100,
                "exam_pass_score": 80,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["job_id"] == "train001"
        assert data["status"] == "running"

    def test_rejects_legacy_exam_type(self):
        """旧版 'exam' 类型应返回 400。"""
        resp = client.post("/generation/jobs", json={"type": "exam", "database": "test_db"})
        assert resp.status_code == 400

    def test_rejects_legacy_readme_type(self):
        """旧版 'readme' 类型应返回 400。"""
        resp = client.post("/generation/jobs", json={"type": "readme", "database": "test_db"})
        assert resp.status_code == 400

    @patch("generation_runner.create_job", side_effect=RuntimeError("已有 1 个生成作业正在运行，请稍后再试"))
    def test_returns_409_when_running_limit_reached(self, mock_create):
        resp = client.post("/generation/jobs", json={"type": "solution", "database": "kb"})
        assert resp.status_code == 409
        assert "正在运行" in resp.json()["detail"]


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
                "path": "generation_output/training_guide.md",
                "size": 1024,
                "modified": "2026-05-09T00:00:00+00:00",
            },
            {
                "name": "solution.md",
                "path": "generation_output/solution.md",
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
            "/generation/artifacts/download?path=generation_output/../../tutor_config.py"
        )
        assert resp.status_code == 400

    def test_rejects_non_allowed_directory(self):
        """不在允许目录中的路径应被拒绝。"""
        resp = client.get("/generation/artifacts/download?path=static/index.html")
        assert resp.status_code == 403

    def test_returns_404_for_missing_file(self):
        """不存在的文件应返回 404。"""
        resp = client.get(
            "/generation/artifacts/download?path=generation_output/nonexistent.md"
        )
        assert resp.status_code == 404

    def test_resolves_public_path_under_external_artifact_root(self, tmp_path):
        artifact_root = tmp_path / "external-output"

        resolved = _resolve_artifact_path(
            "generation_output/report.md",
            artifact_root=artifact_root,
        )

        assert resolved == (artifact_root / "report.md").resolve()

    @pytest.mark.parametrize(
        "path",
        [
            "../report.md",
            "generation_output/../secret.md",
            "C:/absolute/report.md",
            r"C:\absolute\report.md",
            r"C:relative.md",
            r"\\server\share\report.md",
            r"\\?\C:\report.md",
            r"\rooted\report.md",
            "generation_output/bad\x00name.md",
            r"generation_output\..\secret.md",
        ],
    )
    def test_external_artifact_root_rejects_unsafe_paths(self, tmp_path, path):
        with pytest.raises(HTTPException) as exc_info:
            _resolve_artifact_path(path, artifact_root=tmp_path / "external-output")

        assert exc_info.value.status_code == 400

    def test_external_artifact_root_escape_is_forbidden(self, tmp_path, monkeypatch):
        artifact_root = tmp_path / "external-output"
        artifact_root.mkdir()
        outside = tmp_path / "outside"
        original_resolve = Path.resolve

        def resolve_with_external_link(path, *args, **kwargs):
            if path == artifact_root / "linked" / "report.md":
                return outside / "report.md"
            return original_resolve(path, *args, **kwargs)

        monkeypatch.setattr(Path, "resolve", resolve_with_external_link)

        with pytest.raises(HTTPException) as exc_info:
            _resolve_artifact_path(
                "generation_output/linked/report.md",
                artifact_root=artifact_root,
            )

        assert exc_info.value.status_code == 403

    def test_download_rejects_percent_encoded_nul(self):
        resp = client.get("/generation/artifacts/download?path=generation_output/bad%00name.md")

        assert resp.status_code == 400


# ==================== DELETE /generation/artifacts ====================


class TestDeleteArtifact:
    """测试删除历史产物文件。"""

    def test_deletes_artifact_file(self):
        root = Path(__file__).parent.parent.parent
        artifact_dir = root / "generation_output"
        artifact_dir.mkdir(exist_ok=True)
        artifact = artifact_dir / f"delete-api-{uuid4().hex}.md"
        artifact.write_text("# 待删除产物\n", encoding="utf-8")

        try:
            resp = client.delete(
                "/generation/artifacts",
                params={"path": str(artifact.relative_to(root))},
            )
            assert resp.status_code == 200
            assert resp.json()["status"] == "success"
            assert not artifact.exists()
        finally:
            if artifact.exists():
                artifact.unlink()

    def test_rejects_delete_path_traversal(self):
        resp = client.delete(
            "/generation/artifacts",
            params={"path": "generation_output/../../tutor_config.py"},
        )
        assert resp.status_code == 400
