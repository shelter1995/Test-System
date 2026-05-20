from typing import Any


def _trim(text: str, max_chars: int = 700) -> str:
    clean = " ".join(str(text or "").split()).strip()
    if len(clean) <= max_chars:
        return clean
    return clean[:max_chars].rstrip() + "..."


def _as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def extract_source_summaries(contexts: list[dict[str, Any]], max_items: int = 8) -> list[dict[str, Any]]:
    sources = []
    seen = set()
    for ctx in contexts:
        if not isinstance(ctx, dict):
            continue
        meta = ctx.get("metadata") if isinstance(ctx.get("metadata"), dict) else {}
        file_name = str(meta.get("source") or meta.get("file_path") or "知识库资料").strip()
        snippet = _trim(str(ctx.get("text") or ""), 220)
        if not snippet:
            continue
        key = (file_name, snippet)
        if key in seen:
            continue
        seen.add(key)
        source_id = str(ctx.get("source_id") or meta.get("source_id") or "").strip()
        score = _as_float(ctx.get("score"))
        if score is None:
            score = 0.0
        rerank_score = _as_float(ctx.get("rerank_score"))
        chunk_index = ctx.get("chunk_index")
        if chunk_index is None:
            chunk_index = meta.get("chunk_index")
        document_sha256 = str(ctx.get("document_sha256") or meta.get("document_sha256") or "").strip()
        engine = str(ctx.get("engine") or meta.get("engine") or "").strip()
        sources.append(
            {
                "source_id": source_id,
                "file_name": file_name,
                "snippet": snippet,
                "score": score,
                "rerank_score": rerank_score,
                "chunk_index": chunk_index,
                "document_sha256": document_sha256,
                "engine": engine,
            }
        )
        if len(sources) >= max_items:
            break
    return sources


def build_context_fallback_answer(query: str, contexts: list[dict[str, Any]], max_items: int = 3) -> str:
    snippets = []
    for ctx in contexts[:max_items]:
        if not isinstance(ctx, dict):
            continue
        text = _trim(str(ctx.get("text") or ""), 450)
        if text:
            snippets.append(text)

    if not snippets:
        return "当前知识库未找到相关资料。"

    lines = [
        "当前知识库检索到了相关资料，但答案生成服务暂时不可用。",
        "以下是可核对的原文片段：",
    ]
    for index, snippet in enumerate(snippets, start=1):
        lines.append(f"{index}. {snippet}")
    return "\n".join(lines)


def build_kb_answer_prompt(
    query: str,
    contexts: list[dict[str, Any]],
    history: list[dict[str, str]] | None = None,
) -> str:
    lines = [
        "你是企业内部知识库问答助手。",
        "只能基于【知识库资料】回答。",
        "资料不足时回答：当前知识库未找到相关资料。",
        "不要编造价格、流程、政策、日期、版本号或来源。",
        "先给出结论，再给出依据。",
        "关键句后标注来源编号（如 [来源 1]）。",
        "资料不足时明确说明信息缺口。",
        "",
    ]
    if history:
        lines.append("【历史对话】")
        for turn in history[-4:]:
            q = str(turn.get("q") or "").strip()
            a = str(turn.get("a") or "").strip()
            if q:
                lines.append(f"用户：{q}")
            if a:
                lines.append(f"助手：{a}")
        lines.append("")

    lines.append("【知识库资料】")
    if contexts:
        for index, ctx in enumerate(contexts[:8], start=1):
            meta = ctx.get("metadata") if isinstance(ctx.get("metadata"), dict) else {}
            source = meta.get("source") or meta.get("file_path") or "知识库资料"
            source_id = str(ctx.get("source_id") or "").strip() or f"资料{index}"
            lines.append(f"[{source_id}｜来源：{source}]")
            lines.append(_trim(str(ctx.get("text") or ""), 900))
    else:
        lines.append("未检索到可用资料。")

    lines.extend(["", "【用户问题】", str(query or "").strip(), "", "【回答】"])
    return "\n".join(lines)
