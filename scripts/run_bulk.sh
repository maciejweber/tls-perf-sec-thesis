#!/usr/bin/env bash
set -euo pipefail

for bin in curl jq bc; do
  command -v "$bin" >/dev/null || { echo "❌ $bin not found"; exit 1; }
done

HOST="${1-host.docker.internal}"
PORTS=(4431 4432 4433)
REQUESTS="${REQUESTS:-100}"
CONCURRENT="${CONCURRENT:-5}"

echo "==== Test wydajności TLS (bulk throughput) ===="
echo "Host: ${HOST}  Zapytania: ${REQUESTS}  Równoległość: ${CONCURRENT}"
mkdir -p results/raw

measure_request() {
  local host=$1 port=$2
  local start end
  start=$(date +%s.%N)
  curl -k "https://${host}:${port}/" -o /dev/null -s
  end=$(date +%s.%N)
  echo "$end - $start" | bc -l
}

for PORT in "${PORTS[@]}"; do
  echo ""
  echo ">> Testowanie ${HOST}:${PORT}"

  raw_file="results/raw/bulk_${PORT}.txt"
  : > "$raw_file"

  total_time=0
  successful=0

  for i in $(seq 1 "$REQUESTS"); do
    [[ $((i % 10)) -eq 0 ]] && echo -n "."
    t=$(measure_request "$HOST" "$PORT")
    echo "$t" >> "$raw_file"
    total_time=$(echo "$total_time + $t" | bc -l)
    successful=$((successful + 1))
  done
  echo " zakończono!"

  avg_time=$(echo "scale=6; $total_time / $successful" | bc -l)
  avg_time=$(printf "%.6f" "$avg_time")
  rps=$(echo "scale=2; $successful / $total_time" | bc -l)

  echo "* Zapytań na sekundę: $rps"
  echo "* Średni czas zapytania: ${avg_time}s"
  echo "* Udanych zapytań: $successful z $REQUESTS"

  # echo "$rps" > "results/bulk_${PORT}.txt"

  jq -n \
    --arg host "$HOST" \
    --arg port "$PORT" \
    --arg rps "$rps" \
    --arg avg "$avg_time" \
    --arg success "$successful" \
    --arg total "$REQUESTS" \
    '{
      "host": $host,
      "port": ($port|tonumber),
      "requests_per_second": ($rps|tonumber),
      "avg_request_time_s": ($avg|tonumber),
      "successful_requests": ($success|tonumber),
      "total_requests": ($total|tonumber)
    }' > "results/bulk_${PORT}.json"

  echo "Wyniki zapisane w results/bulk_${PORT}.json i ${raw_file}"
done

echo ""
echo "Wszystkie testy zakończone."
