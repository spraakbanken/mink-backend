#!/usr/bin/env bash
# set -x

# Script for creating PDFs from markdown
# Requires markdown, latex and Python pandocfilters

DEVELOPERS_GUIDE_FILES="
../developers-guide.md
"

# Get version number from mink/__init__.py
line=$(grep -F "__version__" ../../mink/__init__.py) # Find version number
version=${line#"__version__ = \""} # Remove prefix
MINK_VERSION=${version%"\""} # Remove suffix


function make_pandoc {
    # Convert markdown to latex/pdf:
    # pandoc -t latex -o $1.tex $1.md \
    # pandoc -t native $1.md \
    pandoc -t latex -o $1.pdf $1.md \
    -H settings_template.tex `# include in header` \
    --template template.tex `# use template`  \
    --toc `# table of contents` \
    -N `# numbered sections` \
    -V urlcolor=RoyalBlue `# color links blue` \
    --listings `# use listings package for LaTeX code blocks`
    #-V links-as-notes=true `# print links as footnotes` \
}


function make_document {
    # $1: file name (without extension)
    # $2: markdown file list
    # $3: Title string

    HEADER="
---
title: Mink Backend $MINK_VERSION - $3
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

    # Concat header and files
    echo -e "$HEADER" > $1.md
    for f in $2
    do
      cat $f >> $1.md
      echo -e "\n" >> $1.md
    done
    make_pandoc $1
}

# Make PDF
make_document developers-guide "$DEVELOPERS_GUIDE_FILES" "Developer's Guide"

# Clean-up
rm developers-guide.md
