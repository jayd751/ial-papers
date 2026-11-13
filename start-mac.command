#!/bin/bash
# Double-click to run the past paper downloader on Mac.
cd "$(dirname "$0")" || exit 1
echo "Starting IAL Papers downloader..."
echo "Your browser will open. Press Ctrl+C in this window to stop."
python3 web.py
