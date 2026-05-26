import sys
import time
from pathlib import Path
from threading import Event


sys.path.insert(0, str(Path(__file__).parent.parent))

import generation_runner


def _wait_for_job_status(job_id: str, statuses: set[str], timeout: float = 1.0) -> dict:
    deadline = time.monotonic() + timeout
    last_job = None
    while time.monotonic() < deadline:
        last_job = generation_runner.get_job(job_id)
        if last_job and last_job.get("status") in statuses:
            return last_job
        time.sleep(0.01)
    raise AssertionError(f"job {job_id} did not reach {statuses}, last={last_job}")


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

    job_id = None
    try:
        started = time.monotonic()
        job_id = generation_runner.create_job({"type": "solution", "database": "kb"})
        elapsed = time.monotonic() - started

        assert elapsed < 0.2
        job = generation_runner.get_job(job_id)
        assert job["status"] == "running"
        assert job["stage"] in {"init", "searching"}
    finally:
        release.set()
        if job_id:
            _wait_for_job_status(job_id, {"completed", "failed"})


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


def test_create_job_recovers_running_job_from_previous_process(monkeypatch, tmp_path):
    import generation_runner

    jobs_dir = tmp_path / "jobs"
    output_dir = tmp_path / "generation_output"
    jobs_dir.mkdir()
    output_dir.mkdir()
    monkeypatch.setattr(generation_runner, "JOBS_DIR", jobs_dir)
    monkeypatch.setattr(generation_runner, "OUTPUT_DIR", output_dir)
    monkeypatch.setattr(generation_runner, "ROOT", tmp_path)
    monkeypatch.setattr(generation_runner, "MAX_RUNNING_JOBS", 1)
    previous_pid = generation_runner.os.getpid() + 10000
    generation_runner._save_job(
        {
            "job_id": "bbbbbbbbbbbb",
            "status": "running",
            "stage": "searching",
            "created_at": generation_runner._now(),
            "updated_at": generation_runner._now(),
            "worker_pid": previous_pid,
            "request": {"type": "solution"},
            "result": None,
            "error": None,
        }
    )

    monkeypatch.setattr(
        generation_runner,
        "_GENERATORS",
        {"solution": lambda request, job_id=None: {"content": "# 标题\n\n" + "正文。" * 50, "filename": "solution.md"}},
    )

    class DummyThread:
        def __init__(self, *args, **kwargs):
            pass

        def start(self):
            pass

    monkeypatch.setattr(generation_runner.threading, "Thread", DummyThread)

    job_id = generation_runner.create_job({"type": "solution", "database": "kb"})

    old_job = generation_runner.get_job("bbbbbbbbbbbb")
    assert job_id != "bbbbbbbbbbbb"
    assert old_job["status"] == "failed"
    assert "已从运行队列恢复" in old_job["error"]


def test_generation_uses_context_texts(monkeypatch):
    from generation_runner import build_context_block

    context = {
        "contexts": [
            {"text": "资料一", "metadata": {"source": "a.md"}},
            {"text": "资料二", "metadata": {"source": "b.md"}},
        ]
    }

    block = build_context_block(context)

    assert "资料一" in block
    assert "来源: a.md" in block
    assert "资料二" in block


def test_rag_result_format_prefers_file_source_over_query_labels():
    rag_results = {
        "image_test 差异化优势 竞品对比": [
            {
                "text": "视频彩铃触达率高。",
                "score": 0.82,
                "metadata": {
                    "database": "image_test",
                    "source": "商务视频彩铃一页纸长图介绍.png",
                    "sources": ["image_test 差异化优势 竞品对比"],
                },
            }
        ]
    }

    block = generation_runner._format_rag_results(rag_results)

    assert "来源文件：商务视频彩铃一页纸长图介绍.png" in block
    assert "image_test 差异化优势 竞品对比" not in block
    assert "知识库" not in block


def test_solution_prompt_requires_inline_file_citations_in_body():
    prompt = generation_runner._build_solution_prompt(
        {"database": "image_test", "client_unit": "福建人科技公司"},
        {"产品查询": [{"text": "产品资料", "metadata": {"source": "产品手册.pdf"}}]},
    )

    assert "正文" in prompt
    assert "每个事实段落" in prompt
    assert "📄来源：`文件名`" in prompt
    assert "不得只在文末集中列来源" in prompt


def test_training_prompts_require_file_name_citations():
    manual_prompt = generation_runner._build_manual_prompt(
        {"database": "image_test"},
        {"培训查询": [{"text": "培训资料", "metadata": {"source": "培训手册.docx"}}]},
    )
    exam_prompt = generation_runner._build_exam_prompt(
        {"database": "image_test"},
        {"考试查询": [{"text": "考试资料", "metadata": {"source": "考试资料.md"}}]},
        "# 讲义\n\n内容",
    )

    assert "每个事实段落" in manual_prompt
    assert "📄来源：`文件名`" in manual_prompt
    assert "不得使用知识库名或检索关键词代替文件名" in manual_prompt
    assert "引用来源必须写具体文件名" in exam_prompt
    assert "考试资料.md" in exam_prompt


def test_markdown_validation_rejects_missing_required_sections():
    incomplete_manual = (
        "# image_test 培训讲义\n\n"
        "## 课程信息\n\n"
        + ("这是一份已经生成到后半部分但仍然缺少最后章节的培训讲义。" * 5)
        + "\n\n## 第五部分：异议处理话术库\n\n"
        + "**客户**：那审核"
    )

    try:
        generation_runner._validate_markdown_artifact(
            incomplete_manual,
            "培训讲义",
            required_sections=["## 第六部分：总结与行动清单"],
        )
    except generation_runner.ContentValidationError as exc:
        assert "缺少必要章节" in str(exc)
        assert "第六部分" in str(exc)
    else:
        raise AssertionError("expected incomplete manual to be rejected")


def test_training_manual_generation_uses_large_token_budget(monkeypatch, tmp_path):
    import generation_runner

    monkeypatch.setattr(generation_runner, "OUTPUT_DIR", tmp_path / "output")
    monkeypatch.setattr(generation_runner, "JOBS_DIR", tmp_path / "jobs")
    generation_runner.OUTPUT_DIR.mkdir(parents=True)
    generation_runner.JOBS_DIR.mkdir(parents=True)
    monkeypatch.setattr(generation_runner, "_search_for_training", lambda db, group="": {})

    calls = []

    def fake_call(prompt, max_tokens=8000, timeout=None, temperature=0.7):
        calls.append({"prompt": prompt, "max_tokens": max_tokens})
        if "培训讲义" in prompt:
            return (
                "# image_test 培训讲义\n\n"
                "## 课程信息\n\n"
                "## 学习目标（布鲁姆分类）\n\n"
                "## 第一部分：课程导入\n\n"
                "## 第二部分：产品知识\n\n"
                "## 第三部分：客户痛点分析（行业矩阵）\n\n"
                "## 第四部分：销售演练\n\n"
                "## 第五部分：异议处理话术库\n\n"
                "## 第六部分：总结与行动清单\n\n"
                "完整内容。" * 20
            )
        return "# 标题\n\n" + "正文内容。" * 50

    monkeypatch.setattr(generation_runner, "_call_minimax", fake_call)

    generation_runner._generate_training({"database": "kb"}, job_id=None)

    assert calls[0]["max_tokens"] >= 16000


def test_training_job_saves_stage_outputs(monkeypatch, tmp_path):
    import generation_runner

    monkeypatch.setattr(generation_runner, "OUTPUT_DIR", tmp_path / "output")
    monkeypatch.setattr(generation_runner, "JOBS_DIR", tmp_path / "jobs")
    generation_runner.OUTPUT_DIR.mkdir(parents=True)
    generation_runner.JOBS_DIR.mkdir(parents=True)
    monkeypatch.setattr(generation_runner, "_search_for_training", lambda db, group="": {})
    def fake_call(prompt, max_tokens=8000, timeout=None, temperature=0.7):
        if "培训讲义" in prompt:
            return (
                "# image_test 培训讲义\n\n"
                "## 课程信息\n\n"
                "## 学习目标（布鲁姆分类）\n\n"
                "## 第一部分：课程导入\n\n"
                "## 第二部分：产品知识\n\n"
                "## 第三部分：客户痛点分析（行业矩阵）\n\n"
                "## 第四部分：销售演练\n\n"
                "## 第五部分：异议处理话术库\n\n"
                "## 第六部分：总结与行动清单\n\n"
                "正文内容。" * 30
            )
        return "# 标题\n\n" + "正文内容。" * 50

    monkeypatch.setattr(generation_runner, "_call_minimax", fake_call)

    result = generation_runner._generate_training({"database": "kb"}, job_id=None)

    filenames = [item["filename"] for item in result["files"]]
    assert any(name.endswith("_培训讲义.md") or "_培训讲义_" in name for name in filenames)
    assert any("_测试题_" in name for name in filenames)
    assert any("_使用说明_" in name for name in filenames)
