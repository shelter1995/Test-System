from typing import Any


def _trim(text: str, max_chars: int = 700) -> str:
    clean = " ".join(str(text or "").split()).strip()
    if len(clean) <= max_chars:
        return clean
    return clean[:max_chars].rstrip() + "..."


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
        sources.append(
            {
                "file_name": file_name,
                "snippet": snippet,
                "score": float(ctx.get("score") or 0),
            }
        )
        if len(sources) >= max_items:
            break
    return sources


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
        "回答应先给结论，再列出关键依据。",
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
            lines.append(f"[资料{index}｜来源：{source}]")
            lines.append(_trim(str(ctx.get("text") or ""), 900))
    else:
        lines.append("未检索到可用资料。")

    lines.extend(["", "【用户问题】", str(query or "").strip(), "", "【回答】"])
    return "\n".join(lines)
