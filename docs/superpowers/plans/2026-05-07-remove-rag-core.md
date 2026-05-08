# Remove rag-core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the old `rag-core` service and make `rag-anything-api` on port 8003 the only knowledge-base entrypoint.

**Architecture:** All active callers should use the compatible REST API exposed by `rag-anything-api`. Legacy direct ChromaDB imports and hard-coded `localhost:8000` calls must be removed or migrated before deleting `rag-core`.

**Tech Stack:** FastAPI, LightRAG/RAG-Anything adapter, Python scripts, Markdown docs, static frontend.

---

### Task 1: Inventory Old RAG Dependencies

**Files:**
- Inspect: all project files outside virtual environments and generated caches

- [ ] Search for `localhost:8000`, `rag-core`, `database.vector`, `ChromaDB`, and `chroma`.
- [ ] Classify each hit as active code, user-facing docs, historical migration notes, or old service files.
- [ ] Only leave historical notes if they explicitly say they are obsolete.

### Task 2: Migrate Active Code

**Files:**
- Modify root utility scripts that still call `localhost:8000`.
- Modify `rag-anything-api/adapters.py` so embedding fallback no longer depends on `../rag-core/models`.
- Modify active docs and skill files to reference `localhost:8003`.

- [ ] Replace old HTTP endpoints with `http://localhost:8003`.
- [ ] Remove direct imports from `rag-core/database` in active scripts.
- [ ] Prefer the compatible `rag-anything-api` REST endpoints.

### Task 3: Delete Old Service

**Files:**
- Delete: `D:\GitHub_WorkSpace\Test-System\rag-core`

- [ ] Stop any process listening on old RAG ports if needed.
- [ ] Verify the resolved delete target is exactly under `D:\GitHub_WorkSpace\Test-System\rag-core`.
- [ ] Remove the `rag-core` directory using PowerShell `Remove-Item -LiteralPath ... -Recurse -Force`.

### Task 4: Verify

**Files:**
- Verify edited Python and JavaScript files.

- [ ] Run Python syntax compilation for changed Python files.
- [ ] Run `node --check` for changed JavaScript files.
- [ ] Verify `http://localhost:8003/status`, `http://localhost:8003/db/list`, and `http://localhost:8002/api/status`.
- [ ] Search again for active `localhost:8000`, `rag-core`, and direct ChromaDB references.

