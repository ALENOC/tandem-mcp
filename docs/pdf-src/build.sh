#!/bin/sh
# Build the two architecture PDFs in docs/ from these LaTeX sources.
# Needs pdflatex and a Chromium build (CHROME=/path/to/chrome) to turn assets/architecture.svg into a PDF.
set -e
cd "$(dirname "$0")"
CHROME="${CHROME:-$(ls "$HOME"/.cache/ms-playwright/chromium-*/chrome-linux*/chrome 2>/dev/null | head -1)}"
cat > diagram.html <<HTML
<!doctype html><style>@page{size:720px 612px;margin:0}html,body{margin:0}img{display:block;width:720px;height:612px}</style>
<img src="../../assets/architecture.svg">
HTML
"$CHROME" --headless=new --no-sandbox --no-pdf-header-footer --print-to-pdf=diagram.pdf "file://$PWD/diagram.html" 2>/dev/null
for doc in architecture architettura; do
  pdflatex -interaction=nonstopmode -halt-on-error "tandem-mcp-$doc.tex" >/dev/null
  pdflatex -interaction=nonstopmode -halt-on-error "tandem-mcp-$doc.tex" >/dev/null
  mv "tandem-mcp-$doc.pdf" ..
done
rm -f diagram.html diagram.pdf ./*.aux ./*.log ./*.out
