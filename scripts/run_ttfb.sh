#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

HOST=localhost
if [[ "$(uname)" == "Darwin" ]]; then
  HOST="host.docker.internal"
fi

if [[ $# -eq 1 ]]; then
  PORTS=("$1")
else
  PORTS=(4431 4432 8443)
fi

OUTDIR="$ROOT_DIR/results"; mkdir -p "$OUTDIR"
TTFB_PAYLOAD_KB=${TTFB_PAYLOAD_KB:-16}

body_file=$(mktemp)
head -c $((TTFB_PAYLOAD_KB * 1024)) /dev/zero > "$body_file"
trap 'rm -f "$body_file"' EXIT

measure_port() {
  local port=$1
  local url="https://${HOST}:${port}/upload"
  local ttfb total
  # Use curl to capture starttransfer and total time; ignore TLS verification by trusting our CA
  ttfb=$(curl --silent --output /dev/null --cacert "$ROOT_DIR/certs/ca.pem" \
         -X POST --data-binary "@${body_file}" --http1.1 \
         -w '%{time_starttransfer}' "$url" || echo "0")
  total=$(curl --silent --output /dev/null --cacert "$ROOT_DIR/certs/ca.pem" \
          -X POST --data-binary "@${body_file}" --http1.1 \
          -w '%{time_total}' "$url" || echo "0")
  jq -n --arg port "$port" --arg ttfb "$ttfb" --arg total "$total" \
    '{port:($port|tonumber), ttfb_s:($ttfb|tonumber), avg_time:($total|tonumber), method:"curl_ttfb_total"}' \
    > "$OUTDIR/ttfb_${port}.json"
}

echo "==== TTFB measurement (curl, payload=${TTFB_PAYLOAD_KB}KB) ===="
for PORT in "${PORTS[@]}"; do
  measure_port "$PORT"
  echo "✓ ${HOST}:${PORT} -> saved results/ttfb_${PORT}.json"
done

echo "✅ TTFB done" 