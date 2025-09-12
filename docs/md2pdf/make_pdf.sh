#!/usr/bin/env bash

# Script for creating PDFs from markdown
# Requires pandoc and latex.

# Define help message
show_help() {
  echo "Usage: $0 [--host HOST] [--port PORT] [-h]"
  echo ""
  echo "Options:"
  echo "  --host HOST       Set the host address from which to get API documentation (default: http://localhost)"
  echo "  --port PORT       Set the port from which to get API documentation (default: 8000)"
  echo "  --common-report   Create the Mink frontend & backend report and exit"
  echo "  -k                Do not remove intermediate files (for debugging)"
  echo "  -h                Show this help message and exit"
}

# Parse command line arguments
HOST="http://localhost"  # Host address to fetch API documentation from
PORT=8000                # Port to fetch API documentation from
COMMON_REPORT=0  # Create common report for both frontend and backend (off by default)
CLEAN=1          # Clean intermediate files by default

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
    --common-report)
      COMMON_REPORT=1
      shift
      ;;
    -k)
     CLEAN=0
     shift
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
OUTPUT_DIR="output"
mkdir -p $OUTPUT_DIR

# Get API documentation in markdown
echo -e "# Mink Backend – API documentation\n" > output/mink_api.md
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

#-----------------------------------------------------------------------------------------------------------------------
# Frontend report
#-----------------------------------------------------------------------------------------------------------------------
frontend_files_dir="mink-frontend"
frontend_report="frontend_report"

if [[ $COMMON_REPORT -eq 1 ]]; then
  # Make sure the output file is empty before starting
  echo "" > "$OUTPUT_DIR/$frontend_report.md"

  # Loop through frontend files and create a combined markdown file
  for file in $frontend_files_dir/*.md; do
    echo "Processing $file ..."
    base_name=$(basename "$file" .md)
    echo -e "\n\n" >> "$OUTPUT_DIR/$frontend_report.md"
    cat $file >> "$OUTPUT_DIR/$frontend_report.md"
  done
  echo -e "\n"

  # # Shift headings by 1 level using Pandoc (no table conversion)
  # pandoc --columns=1000 "$OUTPUT_DIR/$frontend_report.md" --shift-heading-level-by=1 -o "$OUTPUT_DIR/$frontend_report.md"

fi
#-----------------------------------------------------------------------------------------------------------------------

# Define some variables
if [[ $COMMON_REPORT -eq 1 ]]; then
  filename="mink_report"
  title="Mink, Språkbanken's data platform – Technical Report"
  filelist="
$OUTPUT_DIR/$frontend_report.md
../developers-guide.md
output/mink_api.md
"
else
  filename="mink_backend_report"
  title="Mink, Språkbanken's data platform – Technical Report for the Backend $mink_version"
  filelist="
../developers-guide.md
output/mink_api.md
"
fi

header="
---
title: \"$title\"
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
echo -e "$header" > "$OUTPUT_DIR/$filename.md"
if [[ $COMMON_REPORT -eq 1 ]]; then
  cat intro_common_report.md >> "$OUTPUT_DIR/$filename.md"
fi
for f in $filelist; do
  [ -z "$f" ] && continue
  cat $f >> "$OUTPUT_DIR/$filename.md"
  echo -e "\n\n" >> "$OUTPUT_DIR/$filename.md"
done

# Create PDF from markdown using pandoc
if [[ $COMMON_REPORT -eq 1 ]]; then
  echo "Creating common PDF report from markdown for Mink frontend and backend ..."
else
  echo "Creating PDF from markdown for Mink backend v$mink_version ..."
fi

# pandoc -t latex -o "$OUTPUT_DIR/$filename.tex" "$OUTPUT_DIR/$filename.md" `# Convert markdown to tex (for debugging)` \
pandoc -t latex -o "$OUTPUT_DIR/$filename.pdf" "$OUTPUT_DIR/$filename.md" `# Convert markdown to pdf` \
-H settings_template.tex `# include in header` \
--template template.tex `# use template` \
--columns=1000 `# set column width to large number to avoid reformatting of tables ` \
--toc `# table of contents` \
--toc-depth=2 `# limit depth of table of contents to 2 levels` \
--top-level-division=chapter `# treat top-level headings as chapters` \
-N `# numbered sections` \
-V urlcolor=RoyalBlue `# color links blue` \
-V classoption=openany `# chapters can start on any page` \
--listings `# use listings package for LaTeX code blocks` \
--pdf-engine=xelatex

echo "PDF created: $OUTPUT_DIR/$filename.pdf"

# Clean up
if [ "$CLEAN" -eq 1 ]; then
  echo "Cleaning up ..."
  rm -f $OUTPUT_DIR/*.md $OUTPUT_DIR/*.tex
fi

if [[ $COMMON_REPORT -eq 1 ]]; then
  exit 0
fi
