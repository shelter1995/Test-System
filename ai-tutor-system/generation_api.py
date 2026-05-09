"""
内容生成 API 路由

提供以下端点：
- POST   /generation/jobs              创建生成作业
- GET    /generation/jobs/{job_id}     查询作业状态
- GET    /generation/artifacts         列出历史产物
- GET    /generation/artifacts/download 下载产物文件
"""

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional

router = APIRouter(prefix="/generation", tags=["generation"])


# ==================== 数据模型 ====================

class GenerationRequest(BaseModel):
    """内容生成请求"""
    database: Optional[str] = None
    client_unit: str = ""
    product: str = ""


# ==================== API 端点 ====================

@router.post("/jobs")
async def create_generation_job(request: GenerationRequest):
    """
    创建一个内容生成作业。

    请求体包含 database、client_unit、product 等参数。
    返回 job_id 和初始状态 "running"。
    """
    from generation_runner import create_job

    job_id = create_job(request.model_dump())
    return {"job_id": job_id, "status": "running"}


@router.get("/jobs/{job_id}")
async def get_generation_job(job_id: str):
    """
    查询指定作业的状态。

    返回作业的完整信息，包括 status、result 或 error。
    """
    from generation_runner import get_job

    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.get("/artifacts")
async def list_generation_artifacts():
    """
    列出所有历史生成产物。

    返回 training_output 和 solution_output 目录中的 markdown 文件列表。
    """
    from generation_runner import list_artifacts

    return {"artifacts": list_artifacts()}


@router.get("/artifacts/download")
async def download_artifact(path: str):
    """
    下载指定的产物文件。

    安全限制：path 必须以 training_output 或 solution_output 开头，
    且必须位于项目根目录内。
    """
    root = Path(__file__).parent.parent
    try:
        resolved = (root / path).resolve()
        resolved.relative_to(root.resolve())
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid path")

    allowed_dirs = ["training_output", "solution_output"]
    if not any(path.startswith(d) for d in allowed_dirs):
        raise HTTPException(status_code=403, detail="Access denied")

    if not resolved.exists() or not resolved.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(str(resolved), filename=resolved.name)
