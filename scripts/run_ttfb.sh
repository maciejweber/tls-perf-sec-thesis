#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

HOST=localhost
if [[ "$(uname)" == "Darwin" ]]; then
  HOST="localhost"
fi

if [[ $# -eq 1 ]]; then
  PORTS=("$1")
else
  PORTS=(4431 4432 8443 11112 4434 4435)
fi

OUTDIR="$ROOT_DIR/results"; mkdir -p "$OUTDIR"
TTFB_PAYLOAD_KB=${TTFB_PAYLOAD_KB:-16}

# Determine NetEm profile from current network conditions
get_netem_profile() {
  # Check if NetEm is active and determine profile
  if command -v dnctl >/dev/null 2>&1; then
    local pipe_info=$(dnctl list 2>/dev/null | grep "pipe 1" || echo "")
    if [[ -n "$pipe_info" ]]; then
      if echo "$pipe_info" | grep -q "delay 50ms.*plr 0.005"; then
        echo "delay_50ms_loss_0.5"  # P2
      elif echo "$pipe_info" | grep -q "delay 50ms.*plr 0"; then
        echo "delay_50ms"           # P1
      elif echo "$pipe_info" | grep -q "delay 100ms.*plr 0"; then
        echo "delay_100ms"          # P3
      else
        echo "custom"
      fi
    else
      echo "baseline"               # P0 (no NetEm)
    fi
  else
    echo "baseline"
  fi
}

# Create organized folder structure
NETEM_PROFILE=$(get_netem_profile)
TEST_DIR="$OUTDIR/ttfb/${NETEM_PROFILE}_kb${TTFB_PAYLOAD_KB}"

# Clean and create test directory
if [[ "${CLEAN:-1}" == "1" ]]; then
  rm -rf "$TEST_DIR" 2>/dev/null || true
fi
mkdir -p "$TEST_DIR"

echo "==== TTFB measurement (curl, payload=${TTFB_PAYLOAD_KB}KB, Organized Folder Structure) ===="
echo "📁 Test directory: $TEST_DIR"
echo "🌐 NetEm profile: $NETEM_PROFILE"
echo "📦 Payload: ${TTFB_PAYLOAD_KB}KB"
echo ""

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

  ttfb="$total"

  out="$TEST_DIR/ttfb_${port}_kb${TTFB_PAYLOAD_KB}.json"
  jq -n --arg port "$port" --arg ttfb "$ttfb" --arg total "$total" \
    '{port:($port|tonumber), ttfb_s:($ttfb|tonumber), avg_time:($total|tonumber), method:"curl_total_as_ttfb"}' \
    > "$out"
  cp "$out" "$TEST_DIR/ttfb_${port}.json"
}

for PORT in "${PORTS[@]}"; do
  measure_port "$PORT"
  echo "✓ ${HOST}:${PORT} -> saved $TEST_DIR/ttfb_${PORT}.json"
done

echo "✅ TTFB done"
echo "📁 Results saved in: $TEST_DIR/" 