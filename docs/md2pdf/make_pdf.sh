#!/usr/bin/env bash

# Script for creating PDFs from markdown
# Requires pandoc and latex.

# Define help message
show_help() {
  echo "Usage: $0 [--host HOST] [--port PORT] [-h]"
  echo ""
  echo "Options:"
  echo "  --host HOST    Set the host address from which to get API documentation (default: http://localhost)"
  echo "  --port PORT    Set the port from which to get API documentation (default: 8000)"
  echo "  -h             Show this help message and exit"
}

# Parse command line arguments for host and port
HOST="http://localhost"
PORT=8000
while [[ $# -gt 0 ]]; do
  case "$1" in
    --host)
      HOST="$2"
      shift 2
      ;;
    --port)
      PORT="$2"
      shift 2
      ;;
    -h|--help)
      show_help
      exit 0
      ;;
    *)
      shift
      ;;
  esac
done

# Create output directory if it doesn't exist
mkdir -p output

# Get API documentation in markdown
echo -e "# Mink Backend - API documentation\n" > output/mink_api.md
echo "Fetching API documentation from $HOST:$PORT ..."
curl -sS -o output/mink_api.md.tmp $HOST:$PORT/openapi-to-markdown #> /dev/null 2>&1
# Abort if curl fails
if [ $? -ne 0 ]; then
  echo "Error: Failed to fetch API documentation from $HOST:$PORT"
  exit 1
fi
cat output/mink_api.md.tmp >> output/mink_api.md
rm output/mink_api.md.tmp

# Extract mink version number
mink_version=$(grep -P '(?<=__version__ = ").+(?=")' -o ../../mink/main.py)

# Define some variables
filename="mink_backend_documentation"
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

# Concat header and files and create PDF
echo -e "$header" > "output/$filename.md"
for f in $filelist; do
  [ -z "$f" ] && continue
  cat $f >> "output/$filename.md"
  echo -e "\n\n" >> "output/$filename.md"
done

# Create PDF from markdown using pandoc
echo "Creating PDF from markdown for Mink v$mink_version ..."
# pandoc -t latex -o "output/$1.tex" "$1.md" `# Convert markdown to tex (for debugging)` \
pandoc -t latex -o "output/$filename.pdf" "output/$filename.md" `# Convert markdown to pdf` \
-H settings_template.tex `# include in header` \
--template template.tex `# use template` \
--toc `# table of contents` \
--top-level-division=chapter `# treat top-level headings as chapters` \
-N `# numbered sections` \
-V urlcolor=RoyalBlue `# color links blue` \
--listings `# use listings package for LaTeX code blocks`

echo "PDF created: output/$filename.pdf"

# Clean up
rm output/$filename.md output/mink_api.md
