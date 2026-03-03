"""Convert Markdown reports to styled PDFs."""

from __future__ import annotations

import logging
from io import BytesIO
from pathlib import Path

import markdown
from xhtml2pdf import pisa

logger = logging.getLogger(__name__)

# Clean, readable PDF stylesheet — xhtml2pdf supports a subset of CSS
_CSS = """
@page {
    size: letter;
    margin: 0.75in;
}
body {
    font-family: Helvetica, Arial, sans-serif;
    font-size: 10pt;
    line-height: 1.4;
    color: #222;
}
h1 { font-size: 18pt; border-bottom: 2px solid #333; padding-bottom: 4pt; margin-top: 0; }
h2 { font-size: 14pt; color: #1a5276; margin-top: 16pt; border-bottom: 1px solid #ccc; padding-bottom: 3pt; }
h3 { font-size: 12pt; color: #2c3e50; margin-top: 12pt; }
h4 { font-size: 10pt; color: #444; margin-top: 8pt; }
table { width: 100%; margin: 6pt 0; }
th { background-color: #2c3e50; color: white; padding: 4pt 6pt; text-align: left; font-size: 9pt; }
td { padding: 3pt 6pt; border-bottom: 1px solid #ddd; font-size: 9pt; }
a { color: #2980b9; text-decoration: none; }
code { background-color: #f4f4f4; padding: 1pt 3pt; font-size: 9pt; }
hr { border: none; border-top: 1px solid #ccc; margin: 12pt 0; }
ul, ol { padding-left: 18pt; }
li { margin-bottom: 2pt; }
strong { color: #1a5276; }
"""


def markdown_to_pdf(md_path: Path) -> Path:
    """Convert a Markdown file to a styled PDF.

    Returns the path to the generated PDF (same name, .pdf extension).
    """
    md_text = md_path.read_text(encoding="utf-8")

    html_body = markdown.markdown(
        md_text,
        extensions=["tables", "fenced_code", "toc"],
    )

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
