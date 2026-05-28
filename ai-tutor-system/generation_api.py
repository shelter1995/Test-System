"""
内容生成 API 路由

提供以下端点：
- POST   /generation/jobs              创建生成作业（v2 单类型）
- GET    /generation/jobs/{job_id}     查询作业状态
- GET    /generation/artifacts         列出历史产物
- GET    /generation/artifacts/download 下载产物文件
- DELETE /generation/artifacts         删除历史产物
"""

import re
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional

router = APIRouter(prefix="/generation", tags=["generation"])


def _resolve_artifact_path(path: str) -> Path:
    """Resolve and validate a generation artifact path."""
    root = Path(__file__).parent.parent
    artifact_root = (root / "generation_output").resolve()
    if ".." in Path(path).parts:
        raise HTTPException(status_code=400, detail="Invalid path")
    try:
        resolved = (root / path).resolve()
        resolved.relative_to(root.resolve())
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid path")

    try:
        resolved.relative_to(artifact_root)
    except ValueError:
        raise HTTPException(status_code=403, detail="Access denied")

    return resolved


# ==================== 数据模型 ====================

class GenerationRequest(BaseModel):
    """内容生成请求（v3：solution + training 两种类型，支持 RAG 检索）"""
    type: str  # "solution" | "training"
    database: Optional[str] = None

    # 解决方案字段
    client_unit: Optional[str] = None
    decision_maker_role: Optional[str] = None
    relationship_level: Optional[str] = None
    pain_challenges: Optional[str] = None
    pain_scenarios: Optional[str] = None
    pain_dissatisfaction: Optional[str] = None
    decision_focus: Optional[str] = None
    decision_process: Optional[str] = None
    decision_timeline: Optional[str] = None

    # 培训材料字段
    training_theme: Optional[str] = None
    target_customer_group: Optional[str] = None
    trainee_level: Optional[str] = None
    trainee_base: Optional[str] = None
    duration: Optional[str] = None
    training_goals: Optional[str] = None
    focus_areas: Optional[str] = None
    exam_question_count: Optional[int] = None
    exam_question_types: Optional[list[str]] = None
    exam_question_config: Optional[list[dict]] = None  # [{"type":"选择题","count":5}, ...]
    exam_difficulty_distribution: Optional[dict[str, int]] = None
    exam_total_score: Optional[int] = None
    exam_pass_score: Optional[int] = None

    # 向后兼容：旧字段保留但不再使用
    product: Optional[str] = None
    target_audience: Optional[str] = None
    question_count: Optional[int] = None
    question_types: Optional[str] = None
    use_cases: Optional[str] = None


# ==================== API 端点 ====================

@router.post("/jobs")
async def create_generation_job(request: GenerationRequest):
    """
    创建一个内容生成作业（v2 单类型模式）。

    请求体包含 type、database 及对应类型所需的参数（solution 或 training）。
    返回 job_id 和初始状态 "running"。
    """
    from generation_runner import create_job

    valid_types = {"solution", "training"}
    if request.type not in valid_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid type: {request.type}. Must be one of {valid_types}"
        )

    from generation_runner import ContentValidationError

    try:
        job_id = create_job(request.model_dump())
    except ContentValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return {"job_id": job_id, "status": "running"}


@router.get("/jobs/{job_id}")
async def get_generation_job(job_id: str):
    """
    查询指定作业的状态。

    返回作业的完整信息，包括 status、result 或 error。
    """
    if not re.match(r'^[0-9a-f]{12}$', job_id):
        raise HTTPException(status_code=400, detail="Invalid job_id format")
    from generation_runner import get_job

    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.get("/artifacts")
async def list_generation_artifacts():
    """
    列出所有历史生成产物。

    返回 generation_output 目录中的 markdown 文件列表。
    """
    from generation_runner import list_artifacts

    return {"artifacts": list_artifacts()}


@router.get("/artifacts/download")
async def download_artifact(path: str):
    """
    下载指定的产物文件。

    安全限制：path 必须以 generation_output 开头，
    且必须位于项目根目录内。
    """
    resolved = _resolve_artifact_path(path)

    if not resolved.exists() or not resolved.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(str(resolved), filename=resolved.name)


@router.delete("/artifacts")
async def delete_artifact(path: str):
    """删除指定历史产物文件。"""
    resolved = _resolve_artifact_path(path)

    if not resolved.exists() or not resolved.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    try:
        resolved.unlink()
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Delete failed: {exc}") from exc

    return {"status": "success", "message": "Artifact deleted", "path": path}
