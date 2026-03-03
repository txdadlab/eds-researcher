"""Convert Markdown reports to styled PDFs."""

from __future__ import annotations

import logging
import re
from pathlib import Path

import markdown
from xhtml2pdf import pisa

logger = logging.getLogger(__name__)

# Stylesheet tuned for xhtml2pdf's limited CSS subset
_CSS = """
@page {
    size: letter;
    margin: 0.75in;
}
body {
    font-family: Helvetica, Arial, sans-serif;
    font-size: 10pt;
    line-height: 1.5;
    color: #222;
}
h1 {
    font-size: 20pt;
    color: #1a3c5e;
    border-bottom: 2px solid #1a3c5e;
    padding-bottom: 6pt;
    margin-top: 0;
    margin-bottom: 8pt;
}
h2 {
    font-size: 15pt;
    color: #1a5276;
    margin-top: 20pt;
    margin-bottom: 6pt;
    border-bottom: 1px solid #ccc;
    padding-bottom: 4pt;
}
h3 {
    font-size: 12pt;
    color: #2c3e50;
    margin-top: 14pt;
    margin-bottom: 4pt;
}
h4 {
    font-size: 10pt;
    color: #444;
    margin-top: 8pt;
    margin-bottom: 2pt;
}
p {
    margin-top: 2pt;
    margin-bottom: 4pt;
}
table {
    width: 100%;
    margin: 4pt 0 8pt 0;
    border-collapse: collapse;
}
/* Tables with actual headers (quick reference, evidence tables) */
th {
    background-color: #2c3e50;
    color: white;
    padding: 5pt 6pt;
    text-align: left;
    font-size: 9pt;
    border: 1px solid #2c3e50;
}
td {
    padding: 4pt 6pt;
    border: 1px solid #ddd;
    font-size: 9pt;
    vertical-align: top;
}
/* Key-value detail tables (no visible header) */
table.detail-table th {
    display: none;
}
table.detail-table {
    border: none;
    margin: 2pt 0 6pt 0;
}
table.detail-table td {
    border: none;
    border-bottom: 1px solid #eee;
    padding: 3pt 6pt;
}
table.detail-table td:first-child {
    width: 35%;
    font-weight: bold;
    color: #1a5276;
}
a {
    color: #2980b9;
    text-decoration: none;
}
code {
    background-color: #f4f4f4;
    padding: 1pt 3pt;
    font-size: 9pt;
}
hr {
    border: none;
    border-top: 1px solid #ddd;
    margin: 10pt 0;
}
ul, ol {
    padding-left: 18pt;
    margin-top: 2pt;
    margin-bottom: 4pt;
}
li {
    margin-bottom: 3pt;
}
strong {
    color: #1a5276;
}
em {
    color: #555;
}
/* Callout box for the Important notice */
div.callout {
    background-color: #f0f4f8;
    border-left: 4px solid #1a5276;
    padding: 8pt 10pt;
    margin: 8pt 0;
    font-size: 9pt;
}
div.callout strong {
    color: #c0392b;
}
"""


def _preprocess_html(html: str) -> str:
    """Fix HTML patterns that xhtml2pdf handles poorly."""

    # 1. Convert blockquotes to styled callout divs
    html = re.sub(
        r"<blockquote>\s*<p>(.*?)</p>\s*</blockquote>",
        r'<div class="callout"><p>\1</p></div>',
        html,
        flags=re.DOTALL,
    )

    # 2. Identify key-value detail tables (those with empty <th> headers)
    #    and add a class so CSS can style them differently
    html = re.sub(
        r"<table>\s*<thead>\s*<tr>\s*<th>\s*</th>\s*<th>\s*</th>\s*</tr>\s*</thead>",
        '<table class="detail-table"><thead><tr><th></th><th></th></tr></thead>',
        html,
    )

    # 3. Remove completely empty paragraphs that cause extra spacing
    html = re.sub(r"<p>\s*</p>", "", html)

    # 4. Replace problematic unicode characters xhtml2pdf may not render
    replacements = {
        "\u2014": "&mdash;",   # em dash
        "\u2013": "&ndash;",   # en dash
        "\u2018": "&lsquo;",   # left single quote
        "\u2019": "&rsquo;",   # right single quote
        "\u201c": "&ldquo;",   # left double quote
        "\u201d": "&rdquo;",   # right double quote
        "\u2026": "...",       # ellipsis
        "\u2022": "&bull;",    # bullet
    }
    for char, entity in replacements.items():
        html = html.replace(char, entity)

    return html


def markdown_to_pdf(md_path: Path) -> Path:
    """Convert a Markdown file to a styled PDF.

    Returns the path to the generated PDF (same name, .pdf extension).
    """
    md_text = md_path.read_text(encoding="utf-8")

    html_body = markdown.markdown(
        md_text,
        extensions=["tables", "fenced_code", "toc"],
    )

    # Clean up HTML for xhtml2pdf compatibility
    html_body = _preprocess_html(html_body)

    full_html = f"""<!DOCTYPE html>
<html><head>
<meta charset="utf-8">
<style>{_CSS}</style>
</head><body>
{html_body}
</body></html>"""

    pdf_path = md_path.with_suffix(".pdf")
    with open(pdf_path, "wb") as f:
        status = pisa.CreatePDF(full_html, dest=f)

    if status.err:
        logger.error(f"PDF generation had errors: {status.err}")
    else:
        logger.info(f"PDF report written to {pdf_path}")

    return pdf_path
