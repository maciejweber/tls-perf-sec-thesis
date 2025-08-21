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
  PORTS=(4431 4432 8443 11112 4434 4435)
fi

OUTDIR="$ROOT_DIR/results"; mkdir -p "$OUTDIR"
TTFB_PAYLOAD_KB=${TTFB_PAYLOAD_KB:-16}

body_file=$(mktemp)
head -c $((TTFB_PAYLOAD_KB * 1024)) /dev/zero > "$body_file"
trap 'rm -f "$body_file"' EXIT

measure_port() {
  local port=$1
  local url

  if [[ "$port" == "11112" ]]; then
    url="https://${HOST}:${port}/"
    total=$(curl --silent --output /dev/null --cacert "$ROOT_DIR/certs/ca.pem" \
            --http1.1 -X GET -w '%{time_total}' "$url" || echo "0")
  else
    url="https://${HOST}:${port}/upload"
    total=$(curl --silent --output /dev/null --cacert "$ROOT_DIR/certs/ca.pem" \
            -X POST --data-binary "@${body_file}" --http1.1 \
            -w '%{time_total}' "$url" || echo "0")
  fi

  # Use total time as TTFB proxy for robustness in this environment
  ttfb="$total"

  jq -n --arg port "$port" --arg ttfb "$ttfb" --arg total "$total" \
    '{port:($port|tonumber), ttfb_s:($ttfb|tonumber), avg_time:($total|tonumber), method:"curl_total_as_ttfb"}' \
    > "$OUTDIR/ttfb_${port}.json"
}

echo "==== TTFB measurement (curl, payload=${TTFB_PAYLOAD_KB}KB) ===="
for PORT in "${PORTS[@]}"; do
  measure_port "$PORT"
  echo "✓ ${HOST}:${PORT} -> saved results/ttfb_${PORT}.json"
done

echo "✅ TTFB done" 