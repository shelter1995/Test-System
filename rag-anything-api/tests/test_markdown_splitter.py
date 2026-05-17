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
    assert files[0].read_text(encoding="utf-8").startswith(
        "<!-- source: book part: 1/2 -->"
    )
