#!/usr/bin/env bash
set -euo pipefail

echo "==== Test wydajności handshake TLS ===="

HOST=${1:-localhost}
PORTS=(4431 4432 4433)
TEST_TIME=${TEST_TIME:-15}
OUTPUT_DIR="results"
mkdir -p "$OUTPUT_DIR"

for PORT in "${PORTS[@]}"; do
  echo ""
  echo "Testowanie ${HOST}:${PORT} (${TEST_TIME}s, pełny handshake)"

  result=$(openssl s_time -connect "${HOST}:${PORT}" -new -time "${TEST_TIME}" 2>&1 || true)

  summary=$(echo "$result" \
            | grep -E '^[0-9]+ connections in [0-9]+\.[0-9]+s;' \
            | head -n 1)
  if [[ -z "$summary" ]]; then
    echo "❌  Nie udało się sparsować wyniku dla portu ${PORT}"
    continue
  fi

  total_connections=$(echo "$summary" | awk '{print $1}')
  total_time=$(echo "$summary" | awk '{print $4}' | tr -d 's;')
  connections_per_sec=$(echo "$summary" | awk '{print $5}')

  mean_ms=$(awk -v t="$total_time" -v c="$total_connections" 'BEGIN {printf "%.3f", 1000*t/c}')

  echo "* Handshake'ów:            $total_connections"
  echo "* Handshake'ów na sekundę: $connections_per_sec"
  echo "* Średni czas handshake:   ${mean_ms} ms"

  jq -n \
    --arg port  "$PORT" \
    --arg mean  "$mean_ms" \
    --arg total "$total_connections" \
    --arg cps   "$connections_per_sec" \
    --arg tt    "$total_time" \
    '{
       "port":              ($port|tonumber),
       "mean_ms":           ($mean|tonumber),
       "total_connections": ($total|tonumber),
       "connections_per_sec": ($cps|tonumber),
       "test_time_s":       ($tt|tonumber)
     }' > "${OUTPUT_DIR}/handshake_${PORT}.json"

  echo "✔  Wyniki zapisane w ${OUTPUT_DIR}/handshake_${PORT}.json"
done

echo ""
echo "Wszystkie testy zakończone."
