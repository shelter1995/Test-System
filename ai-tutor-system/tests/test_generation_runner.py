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
