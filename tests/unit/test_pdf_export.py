# pyright: reportPrivateUsage=false

"""Safety boundaries for rendering run content into PDFs."""

from typing import Any

import pytest

from glossogen.server.pdf import router
from glossogen.server.pdf.html_renderer import _markdown_to_html


def test_markdown_renderer_escapes_embedded_html() -> None:
    rendered = str(_markdown_to_html('<img src="file:///etc/passwd"> **bold**'))

    assert "&lt;img" in rendered
    assert "<img" not in rendered
    assert "<strong>bold</strong>" in rendered


def test_pdf_generation_disables_resource_fetching(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    class FakeDocument:
        def write_pdf(self) -> bytes:
            return b"pdf"

    def fake_html(**kwargs: Any) -> FakeDocument:
        captured.update(kwargs)
        return FakeDocument()

    monkeypatch.setattr(router.weasyprint, "HTML", fake_html)

    assert router._generate_pdf_bytes("<p>content</p>") == b"pdf"
    fetcher = captured["url_fetcher"]
    with pytest.raises(ValueError, match="Resource loading is disabled"):
        fetcher("file:///etc/passwd")
