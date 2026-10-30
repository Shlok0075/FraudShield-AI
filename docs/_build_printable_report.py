"""
Build a print-ready HTML version of the project report.

The Markdown file is the source of truth; this renders it with print CSS
(A4/Letter, page breaks before top-level sections, repeating table headers)
so the report can be printed or saved to PDF straight from a browser.

    python docs/_build_printable_report.py
"""
import re
from pathlib import Path

import markdown

HERE = Path(__file__).resolve().parent
SRC = HERE / "PROJECT_REPORT.md"
OUT = HERE / "PROJECT_REPORT.html"

TEXT = SRC.read_text(encoding="utf-8")

# Rewrite intra-document links so they resolve against the single HTML file.
TEXT = re.sub(r"\]\(#([^)]+)\)", r'](#\1)', TEXT)

html_body = markdown.markdown(
    TEXT,
    extensions=["tables", "fenced_code", "toc", "sane_lists", "attr_list"],
    extension_configs={"toc": {"permalink": False, "toc_depth": "2-3"}},
)

# Force a page break before every top-level section so each chapter of the
# printed report starts cleanly. The `toc` extension adds id="..." to headings,
# so the opening tag must be matched with its attributes, not as a bare <h2>.
def _add_break(m: re.Match) -> str:
    attrs = m.group(1) or ""
    attrs = re.sub(r'\s*class="[^"]*"', "", attrs)
    return f'<h2{attrs} class="page-break-before">'


html_body, n_breaks = re.subn(r"<h2([^>]*)>", _add_break, html_body)
if n_breaks < 20:
    raise SystemExit(
        f"expected a page break on each of ~27 sections, applied {n_breaks} - "
        "heading markup changed; fix _add_break before printing"
    )
print(f"page breaks applied to {n_breaks} sections")

HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>FraudShield AI &mdash; Complete Project Report</title>
<style>
  /* ---------- print layout ---------- */
  @page { size: A4; margin: 20mm 16mm 18mm 16mm; }

  html { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
  body {
    font-family: "Georgia", "Times New Roman", serif;
    font-size: 10.5pt;
    line-height: 1.5;
    color: #16202b;
    background: #fff;
    margin: 0 auto;
    max-width: 190mm;
    padding: 16mm 8mm;
  }

  /* ---------- headings ---------- */
  h1 {
    font-size: 24pt; text-align: center; margin: 0 0 6pt;
    border-bottom: 3px solid #16202b; padding-bottom: 8pt; letter-spacing: .2px;
  }
  h1 + p { text-align: center; color: #46586b; font-size: 11.5pt; margin-top: 2pt; }
  h1 + h3 { text-align: center; border: 0; margin-top: 2pt; }

  h2 {
    font-size: 15pt; margin: 22pt 0 8pt; padding-bottom: 4pt;
    border-bottom: 1.5px solid #8fa3b5; color: #0f1b26;
  }
  h2.page-break-before { page-break-before: always; break-before: page; }

  h3 { font-size: 12pt; margin: 14pt 0 5pt; color: #1d3346; }
  h4 { font-size: 11pt; margin: 11pt 0 4pt; color: #2b4257; }

  p { margin: 5pt 0; text-align: justify; }
  strong { color: #0f1b26; }

  /* ---------- code ---------- */
  code {
    font-family: "Consolas", "SF Mono", "Courier New", monospace;
    font-size: 8.8pt; background: #f1f4f7; padding: 1px 4px;
    border-radius: 3px; border: 1px solid #dde3ea;
  }
  pre {
    background: #f7f9fb; border: 1px solid #d7dfe8; border-left: 4px solid #4a6b8a;
    padding: 8pt 10pt; border-radius: 4px; overflow-x: auto;
    page-break-inside: avoid; break-inside: avoid;
  }
  pre code { background: none; border: 0; padding: 0; font-size: 8.4pt; line-height: 1.4; }

  /* ---------- tables: the core of the report ---------- */
  table {
    width: 100%; border-collapse: collapse; margin: 9pt 0 12pt;
    font-size: 8.9pt; page-break-inside: auto; break-inside: auto;
  }
  /* repeat the header on every page a long table spans */
  thead { display: table-header-group; }
  tfoot { display: table-footer-group; }
  tr { page-break-inside: avoid; break-inside: avoid; }
  th {
    background: #e7edf3; border: 1px solid #b8c6d3; padding: 4pt 5pt;
    text-align: left; font-weight: bold; color: #10202e;
  }
  td { border: 1px solid #c8d3dd; padding: 3.5pt 5pt; vertical-align: top; }
  tbody tr:nth-child(even) { background: #f7fafc; }

  /* ---------- blockquote (disclaimer) ---------- */
  blockquote {
    margin: 12pt 0; padding: 9pt 12pt;
    background: #fff8e6; border: 1px solid #e0c78a;
    border-left: 5px solid #c8961e; border-radius: 3px;
    page-break-inside: avoid; break-inside: avoid;
  }
  blockquote h2 { border: 0; margin: 0 0 5pt; font-size: 11.5pt; }
  blockquote p { margin: 3pt 0; font-size: 9.4pt; text-align: left; }

  hr { border: 0; border-top: 1px solid #c8d3dd; margin: 14pt 0; }
  ul, ol { margin: 5pt 0; padding-left: 20pt; }
  li { margin: 2.5pt 0; }

  a { color: #14507d; text-decoration: none; }
  a:hover { text-decoration: underline; }

  /* ---------- screen-only view button ---------- */
  .no-print {
    position: fixed; top: 14px; right: 14px;
    background: #16202b; color: #fff; border: 0; cursor: pointer;
    padding: 9px 15px; border-radius: 6px; font-size: 12px;
    font-family: system-ui, sans-serif; box-shadow: 0 2px 8px rgba(0,0,0,.25);
  }
  .no-print:hover { background: #2b3d4f; }
  @media print { .no-print { display: none; } }
</style>
</head>
<body>
<button class="no-print" onclick="window.print()">Print / Save as PDF</button>
__BODY__
</body>
</html>
""".replace("__BODY__", html_body)

OUT.write_text(HTML, encoding="utf-8")

words = len(re.findall(r"\b\w+\b", TEXT))
print(f"Markdown : {SRC}  ({len(TEXT):,} chars, ~{words:,} words)")
print(f"Printable: {OUT}  ({len(HTML):,} chars)")
print("\nTo produce a PDF: open the HTML file and press Ctrl+P (Cmd+P on macOS),")
print('choosing "Save as PDF" as the destination.')
