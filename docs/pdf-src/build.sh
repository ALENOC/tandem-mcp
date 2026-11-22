#!/bin/sh
# Build the two architecture PDFs in docs/ from these LaTeX sources.
# The English PDF uses assets/architecture.svg, the Italian one architettura.svg (same diagram, Italian labels).
# Needs pdflatex and a Chromium build (CHROME=/path/to/chrome) to turn each SVG into a PDF.
set -e
cd "$(dirname "$0")"
CHROME="${CHROME:-$(ls "$HOME"/.cache/ms-playwright/chromium-*/chrome-linux*/chrome 2>/dev/null | head -1)}"
svg_to_pdf() {
  cat > diagram.html <<HTML
<!doctype html><style>@page{size:720px 612px;margin:0}html,body{margin:0}img{display:block;width:720px;height:612px}</style>
<img src="$1">
HTML
  "$CHROME" --headless=new --no-sandbox --no-pdf-header-footer --print-to-pdf="$2" "file://$PWD/diagram.html" 2>/dev/null
}
svg_to_pdf ../../assets/architecture.svg diagram-en.pdf
svg_to_pdf architettura.svg diagram-it.pdf
for doc in architecture architettura; do
  pdflatex -interaction=nonstopmode -halt-on-error "tandem-mcp-$doc.tex" >/dev/null
  pdflatex -interaction=nonstopmode -halt-on-error "tandem-mcp-$doc.tex" >/dev/null
  mv "tandem-mcp-$doc.pdf" ..
done
[ -n "$KEEP_LOGS" ] || rm -f ./*.log
rm -f diagram.html diagram-en.pdf diagram-it.pdf ./*.aux ./*.out
