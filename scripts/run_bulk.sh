#!/usr/bin/env bash

need=(curl jq)
for bin in curl jq; do
  command -v $bin >/dev/null || { echo "❌ $bin not found"; exit 1; }
done

set -euo pipefail
HOST="${1-host.docker.internal}"
PORT="${2-4433}"
REQUESTS="${REQUESTS:-100}"
CONCURRENT="${CONCURRENT:-5}"

echo "==== Test wydajności TLS (bulk throughput) ===="
echo "Testowanie ${HOST}:${PORT} (${CONCURRENT} równoległych połączeń, ${REQUESTS} zapytań)"

mkdir -p results/raw

measure_request() {
  start=$(date +%s.%N)
  curl -k "https://${HOST}:${PORT}/" -o /dev/null -s
  end=$(date +%s.%N)
  echo "$end - $start" | bc
}

echo "Uruchamianie testu wydajności..."
total_time=0
successful=0

for i in $(seq 1 $REQUESTS); do
  if (( i % 10 == 0 )); then
    echo -n "."
  fi
  
  time=$(measure_request)
  total_time=$(echo "$total_time + $time" | bc)
  successful=$((successful + 1))
done

echo " zakończono!"

avg_time=$(echo "scale=6; $total_time / $successful" | bc)
requests_per_second=$(echo "scale=2; $successful / $total_time" | bc)

echo ""
echo "Wyniki dla ${HOST}:${PORT}:"
echo "* Zapytań na sekundę: $requests_per_second"
echo "* Średni czas zapytania: ${avg_time}s"
echo "* Udanych zapytań: $successful z $REQUESTS"

echo "$requests_per_second" > "results/bulk_${PORT}.txt"

jq -n \
  --arg host "$HOST" \
  --arg port "$PORT" \
  --arg rps "$requests_per_second" \
  --arg avg "$avg_time" \
  --arg success "$successful" \
  --arg total "$REQUESTS" \
  '{
    "host": $host,
    "port": $port,
    "requests_per_second": $rps|tonumber,
    "avg_request_time_s": $avg|tonumber,
    "successful_requests": $success|tonumber,
    "total_requests": $total|tonumber
  }' > "results/bulk_${PORT}.json"

echo ""
echo "Test zakończony. Wyniki zapisane w results/bulk_${PORT}.txt i results/bulk_${PORT}.json"