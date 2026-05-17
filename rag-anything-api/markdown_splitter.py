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
        if current and (
            len(prospective) > max_chars or re.match(r"^#{1,3}\s+", block) is not None
        ):
            flush()
        current.append(block)
    flush()

    return segments


def write_markdown_segments(
    segments: list[MarkdownSegment], output_dir: Path, source_stem: str
) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    total = len(segments)
    paths: list[Path] = []
    for segment in segments:
        path = output_dir / f"{source_stem}_part_{segment.index:03d}.md"
        header = f"<!-- source: {source_stem} part: {segment.index}/{total} -->\n\n"
        path.write_text(header + segment.text + "\n", encoding="utf-8")
        paths.append(path)
    return paths
