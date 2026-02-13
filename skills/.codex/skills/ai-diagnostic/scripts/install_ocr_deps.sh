#!/usr/bin/env bash
set -euo pipefail

python3 -m pip install --user -r "$(dirname "$0")/requirements.txt"

# Optional: system tesseract (Ubuntu)
if command -v apt-get >/dev/null 2>&1; then
  if ! command -v tesseract >/dev/null 2>&1; then
    sudo apt-get update
    sudo apt-get install -y tesseract-ocr
  fi
fi

echo "OCR deps installed."
