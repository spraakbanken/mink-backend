#!/usr/bin/env bash

# Script for creating PDFs from markdown
# Requires pandoc and latex.
# Development server needs to be running on localhost:8000
# Usage: ./make_pdf.sh

# Extract version number from ../../mink/main.py
mink_version=$(grep -P '(?<=__version__ = ").+(?=")' -o ../../mink/main.py)

# Get API documentation in markdown
echo -e "# Mink Backend - API documentation\n" > output/mink_api.md
curl -sS -o output/mink_api.md.tmp http://localhost:8000/openapi-to-markdown > /dev/null 2>&1
cat output/mink_api.md.tmp >> output/mink_api.md
rm output/mink_api.md.tmp

# Define some variables
filename="developers-guide"
filelist="
../developers-guide.md
output/mink_api.md
"
header="
---
title: Mink Backend $mink_version - Documentation
author: |
  | Språkbanken Text
  | Institutionen för svenska, flerspråkighet och språkteknologi
  | Göteborgs universitet
  |
  |
  |
  |
  |
  |
  |
  | ![](mink.png){width=6cm}
---
  "

function make_pandoc {
    # # Convert markdown to tex (for debugging)
    # pandoc -t latex -o "output/$1.tex" "$1.md" \
    # Convert markdown to pdf
    pandoc -t latex -o "output/$1.pdf" "output/$1.md" \
    -H settings_template.tex `# include in header` \
    --template template.tex `# use template` \
    --toc `# table of contents` \
    --top-level-division=chapter `# treat top-level headings as chapters` \
    -N `# numbered sections` \
    -V urlcolor=RoyalBlue `# color links blue` \
    --listings `# use listings package for LaTeX code blocks`
}


mkdir -p output

# Concat header and files and create PDF
echo -e "$header" > "output/$filename.md"
for f in $filelist; do
  [ -z "$f" ] && continue
  cat $f >> "output/$filename.md"
  echo -e "\n\n" >> "output/$filename.md"
done
make_pandoc $filename

# Clean up
rm output/$filename.md output/mink_api.md
