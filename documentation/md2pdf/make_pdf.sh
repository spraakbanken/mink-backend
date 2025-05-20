#!/usr/bin/env bash

# Script for creating PDFs from markdown
# Requires markdown, latex and pandoc

# Extract version number from ../../mink/main.py
mink_version=$(grep -P '(?<=__version__ = ").+(?=")' -o ../../mink/main.py)

# Define some variables
filename="developers-guide"
filelist="
../developers-guide.md
"
header="
---
title: Mink Backend $mink_version - Developer's Guide
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
    # Convert markdown to latex/pdf:
    # pandoc -t latex -o "output/$1.tex" "$1.md" \
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

#
for f in "$filelist"; do
    cat "$f" >> "output/tmp.md"
    echo -e "\n" >> "output/tmp.md"
done
pandoc "output/tmp.md" --shift-heading-level-by=1 -o "output/tmp.md"

# Concat header and files and create PDF
echo -e "$header" > "output/$filename.md"
cat "output/tmp.md" >> "output/$filename.md"
# for f in "$filelist"; do
#   cat $f >> "output/$filename.md"
#   echo -e "\n" >> "output/$filename.md"
# done
make_pandoc $filename

# Clean up
rm output/$filename.md
rm output/tmp.md
