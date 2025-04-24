#!/usr/bin/env bash
# ------------------------------------------------------------
# run_bulk.sh — test przepustowości HTTP/2 przy utrzymanym połączeniu TLS
# ------------------------------------------------------------
# Co mierzymy i dlaczego:
#   • wrk2  — kontrola request-rate, metryki latency + RPS
#   • 30 s  — aby wygładzić wahnięcia I/O
#   • zapisujemy tylko Throughput (req/s) – reszta w raw logu
# ------------------------------------------------------------
need=(wrk2 jq openssl)

for bin in openssl jq wrk2; do
  command -v $bin >/dev/null || { echo "❌ $bin not found"; exit 1; }
done

set -euo pipefail
HOST="${1-localhost}"
PORT="${2-4431}"
RATE="${RATE:-1000}"     # req/s
CONN="${CONN:-64}"
THREADS="${THREADS:-8}"

wrk2 -t"$THREADS" -c"$CONN" -d30s -R"$RATE" --latency \
     -H "Host: bench" "https://${HOST}:${PORT}/" 2>&1 \
     | tee "results/raw/wrk2_${PORT}.log" \
     | awk '/Requests\/sec/ {print $2}' \
     >  "results/bulk_${PORT}.txt"
