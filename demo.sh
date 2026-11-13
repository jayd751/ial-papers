#!/bin/bash
# Scripted demo run — record this in a themed terminal.
# Beats are separated by clears + sleeps so you can cut on the beats.
set -e
cd "$(dirname "$0")"
OUT=papers

clear
echo "══════════════════════════════════════════════"
echo " 1 · THE CATALOGUE — what Pearson has indexed"
echo "══════════════════════════════════════════════"
python3 cli.py subjects | head -18
sleep 3
clear

echo "══════════════════════════════════════════════"
echo " 2 · DRILL DOWN — Maths units"
echo "══════════════════════════════════════════════"
python3 cli.py units Mathematics
sleep 3
clear

echo "══════════════════════════════════════════════"
echo " 3 · DRY RUN — exactly what we're about to grab"
echo "══════════════════════════════════════════════"
python3 cli.py download --subject Mathematics --unit WMA11 \
    --years 2023-2024 --sessions Jan Jun Oct --types qp ms \
    --out "$OUT" --dry-run
sleep 3
clear

echo "══════════════════════════════════════════════"
echo " 4 · THE DOWNLOAD — watch the progress bar"
echo "══════════════════════════════════════════════"
python3 cli.py download --subject Mathematics --unit WMA11 \
    --years 2023-2024 --sessions Jan Jun Oct --types qp ms \
    --out "$OUT"
sleep 3
clear

echo "══════════════════════════════════════════════"
echo " 5 · RUN IT AGAIN — resume means zero rework"
echo "══════════════════════════════════════════════"
python3 cli.py download --subject Mathematics --unit WMA11 \
    --years 2023-2024 --sessions Jan Jun Oct --types qp ms \
    --out "$OUT"
sleep 3
clear

echo "══════════════════════════════════════════════"
echo " 6 · THE COLLECTION — one box, everything"
echo "══════════════════════════════════════════════"
python3 cli.py stats --out "$OUT"
sleep 3
clear

echo "══════════════════════════════════════════════"
echo " 7 · ORGANISED ON DISK"
echo "══════════════════════════════════════════════"
find "$OUT" -name "*.pdf" | sort | sed 's|^|  |' | head -14
sleep 3
clear

echo "══════════════════════════════════════════════"
echo " 8 · OPEN A PAPER — real PDF, real mark scheme"
echo "══════════════════════════════════════════════"
open "$(find "$OUT" -name '*_qp.pdf' | head -1)"
open "$(find "$OUT" -name '*_ms.pdf' | head -1)"
sleep 3
clear

echo "══════════════════════════════════════════════"
echo " 9 · THE DASHBOARD — browser opens now"
echo "══════════════════════════════════════════════"
python3 cli.py dashboard --out "$OUT" --open
