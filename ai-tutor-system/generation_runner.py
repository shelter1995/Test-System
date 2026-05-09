"""
内容生成运行器

封装 run_skill_compliance_suite.py 脚本，提供作业管理能力。
- create_job: 创建生成作业并同步执行（v1）
- get_job: 查询作业状态
- list_jobs: 列出所有历史作业
- list_artifacts: 列出产物目录中的 markdown 文件
"""

import json
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path

JOBS_DIR = Path(__file__).parent / "tutor_data" / "generation_jobs"
JOBS_DIR.mkdir(parents=True, exist_ok=True)

# 产物搜索目录（相对于项目根目录）
ARTIFACT_DIRS = ["training_output", "solution_output"]


def _now() -> str:
    """返回当前 UTC 时间的 ISO 格式字符串。"""
    return datetime.now(timezone.utc).isoformat()


def create_job(request: dict) -> str:
    """
    创建一个内容生成作业。

    参数:
        request: 包含 database, client_unit, product 等字段的字典。

    返回:
        job_id: 12 位十六进制作业 ID。
    """
    job_id = uuid.uuid4().hex[:12]
    job = {
        "job_id": job_id,
        "status": "running",
        "created_at": _now(),
        "request": request,
        "result": None,
        "error": None,
    }
    job_path = JOBS_DIR / f"{job_id}.json"
    job_path.write_text(
        json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    # v1: 同步执行生成脚本
    _run_generation(job_id, request)
    return job_id


def get_job(job_id: str) -> dict | None:
    """根据 job_id 查询作业状态，不存在则返回 None。"""
    path = JOBS_DIR / f"{job_id}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def list_jobs() -> list[dict]:
    """列出所有历史作业，按创建时间倒序。"""
    jobs = []
    for f in sorted(JOBS_DIR.glob("*.json"), reverse=True):
        try:
            jobs.append(json.loads(f.read_text(encoding="utf-8")))
        except Exception:
            pass
    return jobs


def _run_generation(job_id: str, request: dict) -> None:
    """
    运行内容生成脚本（v1 同步模式）。

    调用项目根目录下的 run_skill_compliance_suite.py，
    将执行结果写回作业 JSON 文件。
    """
    job_path = JOBS_DIR / f"{job_id}.json"
    try:
        result = subprocess.run(
            ["python", "run_skill_compliance_suite.py"],
            cwd=str(Path(__file__).parent.parent),
            capture_output=True,
            text=True,
            timeout=600,
        )
        job = json.loads(job_path.read_text(encoding="utf-8"))
        if result.returncode == 0:
            job["status"] = "completed"
            job["result"] = {"stdout": result.stdout[-2000:]}
        else:
            job["status"] = "failed"
            job["error"] = result.stderr[-2000:]
        job["finished_at"] = _now()
        job_path.write_text(
            json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception as e:
        job = json.loads(job_path.read_text(encoding="utf-8"))
        job["status"] = "failed"
        job["error"] = str(e)
        job["finished_at"] = _now()
        job_path.write_text(
            json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8"
        )


def list_artifacts() -> list[dict]:
    """
    列出产物目录中的所有 markdown 文件。

    搜索 training_output 和 solution_output 两个目录，
    返回文件名、相对路径、大小和修改时间。
    """
    root = Path(__file__).parent.parent
    artifacts = []
    for output_dir in ARTIFACT_DIRS:
        dir_path = root / output_dir
        if dir_path.exists():
            for f in dir_path.rglob("*.md"):
                artifacts.append(
                    {
                        "name": f.name,
                        "path": str(f.relative_to(root)),
                        "size": f.stat().st_size,
                        "modified": datetime.fromtimestamp(
                            f.stat().st_mtime, tz=timezone.utc
                        ).isoformat(),
                    }
                )
    return artifacts
