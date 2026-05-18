import sys
import time
from pathlib import Path
from threading import Event


sys.path.insert(0, str(Path(__file__).parent.parent))

import generation_runner


def test_create_job_returns_before_generation_finishes(tmp_path, monkeypatch):
    jobs_dir = tmp_path / "jobs"
    output_dir = tmp_path / "generation_output"
    jobs_dir.mkdir()
    output_dir.mkdir()

    monkeypatch.setattr(generation_runner, "ROOT", tmp_path)
    monkeypatch.setattr(generation_runner, "JOBS_DIR", jobs_dir)
    monkeypatch.setattr(generation_runner, "OUTPUT_DIR", output_dir)

    release = Event()

    def slow_solution(request, job_id=None):
        release.wait(timeout=0.5)
        return {"content": "generated", "filename": "solution.md"}

    monkeypatch.setattr(generation_runner, "_GENERATORS", {"solution": slow_solution})

    started = time.monotonic()
    job_id = generation_runner.create_job({"type": "solution", "database": "kb"})
    elapsed = time.monotonic() - started

    try:
        assert elapsed < 0.2
        job = generation_runner.get_job(job_id)
        assert job["status"] == "running"
        assert job["stage"] in {"init", "searching"}
    finally:
        release.set()


def test_create_job_rejects_when_running_limit_reached(monkeypatch, tmp_path):
    import generation_runner

    monkeypatch.setattr(generation_runner, "JOBS_DIR", tmp_path)
    monkeypatch.setattr(generation_runner, "MAX_RUNNING_JOBS", 1)
    generation_runner._save_job(
        {
            "job_id": "aaaaaaaaaaaa",
            "status": "running",
            "stage": "generating",
            "created_at": generation_runner._now(),
            "request": {"type": "solution"},
            "result": None,
            "error": None,
        }
    )

    try:
        generation_runner.create_job({"type": "training", "database": "kb"})
    except RuntimeError as exc:
        assert "已有 1 个生成作业正在运行" in str(exc)
    else:
        raise AssertionError("expected running job limit error")


def test_training_job_saves_stage_outputs(monkeypatch, tmp_path):
    import generation_runner

    monkeypatch.setattr(generation_runner, "OUTPUT_DIR", tmp_path / "output")
    monkeypatch.setattr(generation_runner, "JOBS_DIR", tmp_path / "jobs")
    generation_runner.OUTPUT_DIR.mkdir(parents=True)
    generation_runner.JOBS_DIR.mkdir(parents=True)
    monkeypatch.setattr(generation_runner, "_search_for_training", lambda db, group="": {})
    monkeypatch.setattr(
        generation_runner,
        "_call_minimax",
        lambda prompt, max_tokens=8000, timeout=None, temperature=0.7: "# 标题\n\n" + "正文内容。" * 50,
    )

    result = generation_runner._generate_training({"database": "kb"}, job_id=None)

    filenames = [item["filename"] for item in result["files"]]
    assert any(name.endswith("_培训讲义.md") or "_培训讲义_" in name for name in filenames)
    assert any("_测试题_" in name for name in filenames)
    assert any("_使用说明_" in name for name in filenames)
