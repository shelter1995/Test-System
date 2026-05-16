# Large PDF Resumable Ingest Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make large PDF knowledge-base ingestion recoverable, staged, and visible so a single LightRAG chunk timeout does not leave the file permanently stuck in `processing`.

**Architecture:** Keep MinerU + RAGAnything + LightRAG as the core stack, but split the ingest lifecycle into explicit stages: upload, MinerU parse, baseline searchable text import, graph enrichment, final reconciliation. Large PDFs should use MinerU markdown output as a stable intermediate artifact and ingest it in smaller markdown segments. Registry and UI must support `processing`, `已导入`, `partial_success`, and `error`.

**Tech Stack:** FastAPI, RAGAnything, LightRAG, MinerU, JSON registry storage, vanilla JS frontend, pytest.

---

## Current Evidence

- MinerU is installed and available from `.venv\Scripts\mineru.EXE`.
- The frontend was not the root cause of the stuck state.
- `kv_store_doc_status.json` showed:
  - `[美少女外拍动作图解×100].黑面.影印版.pdf`: duplicate of an already processed document.
  - `《上帝的眼睛：摄影的哲学》.pdf`: failed at `C[75/134]` with `LLM func: Worker execution timeout after 360s`.
- The immediate status reconciliation fix already maps LightRAG final state back to the registry when documents are listed.

## File Structure

- Modify: `rag-anything-api/database_registry.py`
  - Store richer document metadata: `status`, `error`, `stage`, `segments_total`, `segments_done`, `segments_failed`, `partial_errors`.
- Modify: `rag-anything-api/app.py`
  - Keep upload API contract.
  - Add retry endpoint.
  - Emit staged progress events.
  - Reconcile LightRAG status into registry.
- Create: `rag-anything-api/markdown_splitter.py`
  - Split MinerU markdown output into bounded segment files with stable names.
- Create: `rag-anything-api/ingest_jobs.py`
  - Shared helpers for choosing ingest strategy and recording segment outcomes.
- Modify: `rag-anything-api/raganything_service.py`
  - Add a recoverable large-PDF path that can ingest existing MinerU `.md` output in segments.
- Modify: `ai-tutor-system/static/js/knowledge.js`
  - Render partial success and detailed error tooltip.
- Modify: `ai-tutor-system/static/css/style.css`
  - Add partial status style.
- Test: `rag-anything-api/tests/test_markdown_splitter.py`
- Test: `rag-anything-api/tests/test_database_registry.py`
- Test: `rag-anything-api/tests/test_database_management_api.py`
- Test: `rag-anything-api/tests/test_raganything_service.py`

---

### Task 1: Registry Supports Partial Progress

**Files:**
- Modify: `rag-anything-api/database_registry.py`
- Test: `rag-anything-api/tests/test_database_registry.py`

- [ ] **Step 1: Write the failing tests**

Add tests for recording staged progress and partial success:

```python
def test_update_document_progress_records_stage_and_segment_counts(tmp_path):
    registry = DatabaseRegistry(tmp_path / "databases.json")
    registry.register_database("kb")
    registry.register_document(
        "kb",
        file_name="book.pdf",
        file_path="book.pdf",
        sha256="abc",
        status="processing",
    )

    updated = registry.update_document_progress(
        "kb",
        "abc",
        stage="graph_enrichment",
        segments_total=10,
        segments_done=4,
        segments_failed=1,
        partial_errors=["segment 5 timeout"],
    )

    assert updated is True
    doc = registry.list_documents("kb")[0]
    assert doc["stage"] == "graph_enrichment"
    assert doc["segments_total"] == 10
    assert doc["segments_done"] == 4
    assert doc["segments_failed"] == 1
    assert doc["partial_errors"] == ["segment 5 timeout"]
```

```python
def test_update_document_status_preserves_progress_metadata(tmp_path):
    registry = DatabaseRegistry(tmp_path / "databases.json")
    registry.register_database("kb")
    registry.register_document(
        "kb",
        file_name="book.pdf",
        file_path="book.pdf",
        sha256="abc",
        status="processing",
    )
    registry.update_document_progress("kb", "abc", stage="graph_enrichment", segments_total=3)

    registry.update_document_status("kb", "abc", status="partial_success", error="1 segment failed")

    doc = registry.list_documents("kb")[0]
    assert doc["status"] == "partial_success"
    assert doc["stage"] == "graph_enrichment"
    assert doc["segments_total"] == 3
    assert doc["error"] == "1 segment failed"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest rag-anything-api\tests\test_database_registry.py -q
```

Expected: fail because `update_document_progress` does not exist.

- [ ] **Step 3: Implement minimal registry progress method**

Add `update_document_progress(database_id, sha256, **progress)` beside `update_document_status`. It should update only known progress fields:

```python
allowed = {
    "stage",
    "segments_total",
    "segments_done",
    "segments_failed",
    "partial_errors",
}
```

Also make `register_document` initialize:

```python
"stage": "",
"segments_total": 0,
"segments_done": 0,
"segments_failed": 0,
"partial_errors": [],
```

- [ ] **Step 4: Run tests to verify pass**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest rag-anything-api\tests\test_database_registry.py -q
```

Expected: pass.

---

### Task 2: Markdown Splitter For MinerU Output

**Files:**
- Create: `rag-anything-api/markdown_splitter.py`
- Test: `rag-anything-api/tests/test_markdown_splitter.py`

- [ ] **Step 1: Write failing tests**

```python
from markdown_splitter import split_markdown_text, write_markdown_segments


def test_split_markdown_text_keeps_headings_and_limits_size():
    text = "# Ch1\n" + ("a" * 120) + "\n# Ch2\n" + ("b" * 120)

    segments = split_markdown_text(text, max_chars=150)

    assert len(segments) == 2
    assert segments[0].title == "Ch1"
    assert segments[0].text.startswith("# Ch1")
    assert segments[1].title == "Ch2"
    assert segments[1].text.startswith("# Ch2")


def test_write_markdown_segments_creates_stable_files(tmp_path):
    segments = split_markdown_text("# Intro\nhello\n# Body\nworld", max_chars=50)

    files = write_markdown_segments(segments, tmp_path, source_stem="book")

    assert [path.name for path in files] == ["book_part_001.md", "book_part_002.md"]
    assert files[0].read_text(encoding="utf-8").startswith("<!-- source: book part: 1/2 -->")
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest rag-anything-api\tests\test_markdown_splitter.py -q
```

Expected: fail because module does not exist.

- [ ] **Step 3: Implement splitter**

Implement:

```python
from dataclasses import dataclass
from pathlib import Path
import re


@dataclass(frozen=True)
class MarkdownSegment:
    index: int
    title: str
    text: str


def split_markdown_text(text: str, max_chars: int = 12000) -> list[MarkdownSegment]:
    content = str(text or "").strip()
    if not content:
        return []

    blocks = re.split(r"(?m)(?=^#{1,3}\s+)", content)
    blocks = [block.strip() for block in blocks if block.strip()]
    segments: list[MarkdownSegment] = []
    current: list[str] = []

    def flush() -> None:
        if not current:
            return
        segment_text = "\n\n".join(current).strip()
        match = re.search(r"(?m)^#{1,3}\s+(.+)$", segment_text)
        title = match.group(1).strip() if match else f"part-{len(segments) + 1}"
        segments.append(MarkdownSegment(len(segments) + 1, title, segment_text))
        current.clear()

    for block in blocks:
        prospective = "\n\n".join([*current, block]).strip()
        if current and len(prospective) > max_chars:
            flush()
        current.append(block)
    flush()

    return segments


def write_markdown_segments(segments: list[MarkdownSegment], output_dir: Path, source_stem: str) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    total = len(segments)
    paths: list[Path] = []
    for segment in segments:
        path = output_dir / f"{source_stem}_part_{segment.index:03d}.md"
        header = f"<!-- source: {source_stem} part: {segment.index}/{total} -->\n\n"
        path.write_text(header + segment.text + "\n", encoding="utf-8")
        paths.append(path)
    return paths
```

- [ ] **Step 4: Run tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest rag-anything-api\tests\test_markdown_splitter.py -q
```

Expected: pass.

---

### Task 3: Recover Failed PDF From Existing MinerU Markdown

**Files:**
- Modify: `rag-anything-api/raganything_service.py`
- Test: `rag-anything-api/tests/test_raganything_service.py`

- [ ] **Step 1: Write failing test**

Add a fake service test that proves an existing MinerU `.md` file can be split and each segment ingested:

```python
def test_recover_file_from_markdown_segments_updates_partial_status(tmp_path):
    registry = DatabaseRegistry(tmp_path / "databases.json")
    service = RAGAnythingService(storage_root=tmp_path / "storage", output_root=tmp_path / "output", registry=registry)
    registry.register_database("kb")
    source = tmp_path / "book.pdf"
    source.write_bytes(b"pdf")
    registry.register_document("kb", "book.pdf", str(source), "abc", status="processing")
    mineru_dir = tmp_path / "output" / "kb" / "book_12345678"
    mineru_dir.mkdir(parents=True)
    (mineru_dir / "book.md").write_text("# A\nhello\n# B\nworld", encoding="utf-8")

    calls = []

    def fake_ingest(database_id, file_path, source=None):
        calls.append(Path(file_path).name)
        if file_path.name.endswith("002.md"):
            raise RuntimeError("segment timeout")
        return {"status": "success"}

    service.ingest_file_sync = fake_ingest

    result = service.recover_from_mineru_markdown("kb", source, "abc", max_chars=10)

    assert result["status"] == "partial_success"
    assert calls == ["book_part_001.md", "book_part_002.md"]
    doc = registry.list_documents("kb")[0]
    assert doc["status"] == "partial_success"
    assert doc["segments_total"] == 2
    assert doc["segments_done"] == 1
    assert doc["segments_failed"] == 1
```

- [ ] **Step 2: Run test to verify fail**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest rag-anything-api\tests\test_raganything_service.py::test_recover_file_from_markdown_segments_updates_partial_status -q
```

Expected: fail because `recover_from_mineru_markdown` does not exist.

- [ ] **Step 3: Implement service method**

Implement method behavior:

1. Locate latest MinerU output directory under `output/{db_id}` whose name starts with the PDF stem.
2. Locate `{stem}.md`.
3. Split markdown into segment files under `storage/raganything/{db_id}/segments/{sha256}/`.
4. For each segment, call `ingest_file_sync`.
5. Update registry after each segment.
6. Final status:
   - all passed: `已导入`
   - at least one passed and one failed: `partial_success`
   - all failed: `error`

- [ ] **Step 4: Run test**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest rag-anything-api\tests\test_raganything_service.py -q
```

Expected: pass.

---

### Task 4: Retry Endpoint

**Files:**
- Modify: `rag-anything-api/app.py`
- Test: `rag-anything-api/tests/test_database_management_api.py`

- [ ] **Step 1: Write failing API test**

```python
def test_retry_document_uses_segment_strategy(monkeypatch, tmp_path):
    client, service = _make_client(monkeypatch)
    service.registry.register_database("kb")
    service.registry.register_document(
        "kb",
        file_name="book.pdf",
        file_path=str(tmp_path / "book.pdf"),
        sha256="abc",
        status="error",
        error="timeout",
    )
    calls = []

    def recover(database_id, file_path, sha256, max_chars=12000):
        calls.append((database_id, Path(file_path).name, sha256))
        service.registry.update_document_status(database_id, sha256, "partial_success", "1 segment failed")
        return {"status": "partial_success"}

    service.recover_from_mineru_markdown = recover

    response = client.post("/db/kb/documents/abc/retry", json={"strategy": "markdown_segments"})

    assert response.status_code == 200
    assert response.json()["status"] == "partial_success"
    assert calls == [("kb", "book.pdf", "abc")]
```

- [ ] **Step 2: Run test to verify fail**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest rag-anything-api\tests\test_database_management_api.py::TestRetryDocument -q
```

Expected: fail because endpoint does not exist.

- [ ] **Step 3: Implement endpoint**

Add:

```python
class RetryDocumentRequest(BaseModel):
    strategy: str = "markdown_segments"
    max_chars: int = 12000
```

Add endpoint:

```python
@app.post("/db/{db_id}/documents/{sha256}/retry")
async def retry_document(db_id: str, sha256: str, request: RetryDocumentRequest):
    service = _require_service()
    docs = service.registry.list_documents(db_id)
    doc = next((item for item in docs if item.get("sha256") == sha256), None)
    if doc is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    if request.strategy != "markdown_segments":
        raise HTTPException(status_code=400, detail="仅支持 markdown_segments")
    result = service.recover_from_mineru_markdown(
        db_id,
        Path(doc["file_path"]),
        sha256,
        max_chars=request.max_chars,
    )
    return result
```

- [ ] **Step 4: Run API tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest rag-anything-api\tests\test_database_management_api.py -q
```

Expected: pass.

---

### Task 5: Frontend Status Display For Partial Success

**Files:**
- Modify: `ai-tutor-system/static/js/knowledge.js`
- Modify: `ai-tutor-system/static/css/style.css`

- [ ] **Step 1: Update status mapping**

Change `statusMap`:

```javascript
const statusMap = {
    'imported': '已导入',
    '已导入': '已导入',
    'completed': '已完成',
    'ready': '就绪',
    'processing': '处理中',
    'partial_success': '部分成功',
    'error': '失败'
};
```

Change class logic:

```javascript
const isPartial = !isUploading && rawStatus === 'partial_success';
const statusClass = isDone ? 'status-success' : (isError ? 'status-error' : (isPartial ? 'status-partial' : 'status-pending'));
```

Set tooltip to include error and segment count:

```javascript
const progressText = item.segments_total
    ? `分段: ${item.segments_done || 0}/${item.segments_total}, 失败: ${item.segments_failed || 0}`
    : '';
const titleText = escapeHtml([progressText, item.error || ''].filter(Boolean).join(' | '));
```

- [ ] **Step 2: Add CSS**

```css
.status-text.status-partial {
    background: #e7f1ff;
    color: #084298;
}
```

- [ ] **Step 3: Manual verification**

Open `http://localhost:8002`, go to knowledge base, confirm:

- `已导入` is green.
- `失败` is red.
- `部分成功` is blue.
- Hovering status shows segment/error detail.

---

### Task 6: Apply Retry To Current Failed PDF

**Files:**
- No code changes expected.

- [ ] **Step 1: Ensure services run from `.venv`**

Run:

```powershell
Get-NetTCPConnection -LocalPort 8003,8002 -State Listen | Select-Object LocalPort,OwningProcess
```

Then verify process command lines point to:

```text
D:\GitHub_WorkSpace\Test-System\.venv\Scripts\python.exe
```

- [ ] **Step 2: Call retry endpoint**

Run:

```powershell
$body = @{ strategy = "markdown_segments"; max_chars = 12000 } | ConvertTo-Json
Invoke-RestMethod -Uri http://localhost:8003/db/camera_skill/documents/1907c028f3ddb7eca9a4a3f12cd4c6dd7613a712a6a18b4a780f96a1b4398d0d/retry -Method POST -Body $body -ContentType "application/json" | ConvertTo-Json -Depth 8
```

Expected: `status` is `已导入` or `partial_success`. It should not remain `processing`.

- [ ] **Step 3: Verify UI**

Open knowledge base. Expected:

- `[美少女外拍动作图解×100].黑面.影印版.pdf`: `已导入`
- `《上帝的眼睛：摄影的哲学》.pdf`: `已导入` or `部分成功`
- No permanent `处理中` rows after retry completion.

---

### Task 7: Full Verification

**Files:**
- No code changes.

- [ ] **Step 1: Run backend and frontend tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest rag-anything-api\tests ai-tutor-system\tests -q
```

Expected: all tests pass.

- [ ] **Step 2: Check status endpoints**

Run:

```powershell
Invoke-RestMethod -Uri http://localhost:8003/status -TimeoutSec 5 | ConvertTo-Json -Depth 5
Invoke-RestMethod -Uri http://localhost:8002/api/status -TimeoutSec 5 | ConvertTo-Json -Depth 5
```

Expected:

- RAG service `engine` is `ready`.
- `mineru_available`, `ffmpeg_available`, and `whisper_available` are `true`.
- Tutor backend points to `http://localhost:8003`.

- [ ] **Step 3: Browser verification**

Use Chrome page `http://localhost:8002`.

Verify:

- Upload log shows stages instead of only a single `正在 RAG 解析`.
- Failed/partial status is visible in the file table.
- Reloading the page preserves final status.

---

## Execution Notes

- Do not solve large-PDF failures by only raising timeout.
- Keep timeout increase, if any, as a last-mile safety change after segmentation is working.
- Do not delete existing MinerU output; the retry path should reuse it.
- Do not remove existing LightRAG storage; current processed documents are still useful.
- If duplicate content is detected and original is processed, treat the uploaded document as `已导入`.
- If at least one segment imports successfully and at least one fails, report `partial_success`, not `error`.

## Self-Review

- Spec coverage: covers large PDF timeout, recovery of current failed PDF, frontend visibility, backend status persistence, and tests.
- Placeholder scan: no TBD/TODO placeholders remain.
- Type consistency: planned fields are `stage`, `segments_total`, `segments_done`, `segments_failed`, `partial_errors`; frontend and backend use the same names.
