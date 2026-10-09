# pyright: reportPrivateUsage=false, reportUnknownMemberType=false

"""Safety boundaries for rendering run content into PDFs."""

import pytest

from glossogen.server.pdf.html_renderer import _markdown_to_html
from glossogen.server.pdf.router import _DENY_RESOURCE_FETCHER, _generate_pdf_bytes


def test_markdown_renderer_escapes_embedded_html() -> None:
    rendered = str(_markdown_to_html('<img src="file:///etc/passwd"> **bold**'))

    assert "&lt;img" in rendered
    assert "<img" not in rendered
    assert "<strong>bold</strong>" in rendered


def test_markdown_renderer_does_not_double_escape_code_or_disable_blockquotes() -> None:
    rendered = str(_markdown_to_html("`a<b`\n\n> quoted"))

    assert "<code>a&lt;b</code>" in rendered
    assert "&amp;lt;" not in rendered
    assert "<blockquote>" in rendered


def test_pdf_generation_ignores_image_references_without_fetching_them() -> None:
    pdf = _generate_pdf_bytes('<p>content</p><img src="file:///etc/passwd">')

    assert pdf.startswith(b"%PDF-")


def test_pdf_resource_fetcher_rejects_local_and_network_urls() -> None:
    with pytest.raises(ValueError, match="disallowed protocol"):
        _DENY_RESOURCE_FETCHER.fetch("file:///etc/passwd")
    with pytest.raises(ValueError, match="disallowed protocol"):
        _DENY_RESOURCE_FETCHER.fetch("https://example.test/image.png")
