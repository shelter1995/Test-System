from raganything.parser import Parser


def test_reportlab_text_escape_handles_html_break_tags():
    escaped = Parser._escape_reportlab_text("流程<br>下一步 <tag> & value")

    assert "<br>" not in escaped.lower()
    assert "&lt;tag&gt;" in escaped
    assert "&amp;" in escaped
