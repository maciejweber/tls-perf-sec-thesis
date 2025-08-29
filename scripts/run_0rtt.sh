#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

HOST=localhost
if [[ "$(uname)" == "Darwin" ]]; then
  HOST="localhost"
  DOCKER_NET=""
  export DOCKER_USE_HOST_NET="0"
else
  DOCKER_NET="--network host"
  export DOCKER_USE_HOST_NET="1"
fi

if [[ $# -eq 1 ]]; then
  PORTS=("$1")
else
  PORTS=(4431 4432 8443)
fi

COUNT=${COUNT:-5}
OUTDIR="$ROOT_DIR/results"; mkdir -p "$OUTDIR"
EARLY_DATA_MB=${EARLY_DATA_MB:-4}
TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/tls0rtt.XXXXXX")"; trap 'rm -rf "$TMP_DIR"' EXIT

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
AES_TAG=$([[ "${OPENSSL_ia32cap:-}" == "~0x200000200000000" ]] && echo "aes_off" || echo "aes_on")
TEST_DIR="$OUTDIR/0rtt/${NETEM_PROFILE}_${AES_TAG}_ed${EARLY_DATA_MB}_n${COUNT}"

# Clean and create test directory
rm -rf "$TEST_DIR" 2>/dev/null || true
mkdir -p "$TEST_DIR"

echo "==== 0-RTT Performance Test (${EARLY_DATA_MB}MB early data, ${COUNT} requests) ===="
echo "📁 Test directory: $TEST_DIR"
echo "🌐 NetEm profile: $NETEM_PROFILE"
echo "🔐 AES status: $AES_TAG"
echo "📦 Early data: ${EARLY_DATA_MB}MB, Count: ${COUNT}"
echo ""

build_early_data_file() {
  local port=$1
  local ed_file="$TMP_DIR/early_${port}.bin"
  local bytes
  bytes=$(awk -v m="$EARLY_DATA_MB" 'BEGIN{printf "%d", m*1048576}')
  : > "$ed_file"
  printf 'POST /upload HTTP/1.1\r\nHost: %s\r\nContent-Length: %d\r\nConnection: close\r\n\r\n' "$HOST" "$bytes" >> "$ed_file"
  head -c "$bytes" /dev/zero >> "$ed_file"
  echo "$ed_file"
}

establish_session() {
  local port=$1
  local sess_file="$TMP_DIR/sess_${port}.bin"
  docker run --rm ${DOCKER_NET:+$DOCKER_NET} \
    -e OPENSSL_ia32cap="${OPENSSL_ia32cap:-}" \
    -v "$ROOT_DIR/certs:/certs:ro" \
    -v "$TMP_DIR:/tmp_sess" \
    openquantumsafe/oqs-ossl3 \
      sh -lc "
        if [ $port -eq 8443 ]; then
          openssl s_client -quiet -tls1_3 \
            -provider default -provider oqsprovider \
            -groups X25519MLKEM768 \
            -CAfile /certs/ca.pem \
            -sess_out /tmp_sess/sess_${port}.bin \
            -connect ${HOST}:${port} </dev/null >/dev/null 2>&1 || true
        else
          openssl s_client -quiet -tls1_3 \
            -provider default \
            -CAfile /certs/ca.pem \
            -sess_out /tmp_sess/sess_${port}.bin \
            -connect ${HOST}:${port} </dev/null >/dev/null 2>&1 || true
        fi
      "
}

resume_with_0rtt() {
  local port=$1
  local ed_file="$2"
  python3 - "$port" "$ROOT_DIR" "$TMP_DIR" "$HOST" "$ed_file" <<'PY'
import sys, subprocess, time, os
port = int(sys.argv[1])
root = sys.argv[2]
tmp = sys.argv[3]
host = sys.argv[4]
ed = sys.argv[5]
use_host_net = os.environ.get("DOCKER_USE_HOST_NET", "1") == "1"
base = [
  "docker","run","--rm"
] + (["--network","host"] if use_host_net else []) + [
  "-e","OPENSSL_ia32cap=" + os.environ.get("OPENSSL_ia32cap", ""),
  "-v", f"{root}/certs:/certs:ro",
  "-v", f"{tmp}:/tmp_sess",
  "openquantumsafe/oqs-ossl3","sh","-lc"
]
if port == 8443:
  cmd = (
    "openssl s_client -quiet -tls1_3 "
    "-provider default -provider oqsprovider -groups X25519MLKEM768 "
    "-CAfile /certs/ca.pem -sess_in /tmp_sess/sess_%d.bin "
    "-early_data /tmp_sess/%s -connect %s:%d >/dev/null 2>&1"
  ) % (port, os.path.basename(ed), host, port)
else:
  cmd = (
    "openssl s_client -quiet -tls1_3 -provider default "
    "-CAfile /certs/ca.pem -sess_in /tmp_sess/sess_%d.bin "
    "-early_data /tmp_sess/%s -connect %s:%d >/dev/null 2>&1"
  ) % (port, os.path.basename(ed), host, port)
start = time.perf_counter()
subprocess.run(base + [cmd], check=False)
elapsed = time.perf_counter() - start
print(f"{elapsed:.6f}")
PY
}

measure () {
  local port=$1
  local ed_file
  ed_file=$(build_early_data_file "$port")
  establish_session "$port"
  resume_with_0rtt "$port" "$ed_file"
}

echo "==== True 0-RTT TLS (session resumption + early data) ===="
for PORT in "${PORTS[@]}"; do
  total=0
  for _ in $(seq "$COUNT"); do
    t=$(measure "$PORT")
    total=$(echo "$total + ${t:-0}" | bc -l)
  done
  avg=$(echo "scale=6; $total/$COUNT" | bc -l)
  printf "→ %s:%s  0-RTT avg=%.6fs (early_data=%sMB)\n" "$HOST" "$PORT" "$avg" "$EARLY_DATA_MB"

  out="$TEST_DIR/simple_${PORT}_ed${EARLY_DATA_MB}_n${COUNT}.json"
  jq -n --arg avg "$avg" '{avg_time:($avg|tonumber), method:"openssl_s_client_0rtt_host_timed"}' \
       > "$out"
  cp "$out" "$TEST_DIR/simple_${PORT}.json"

done

echo "✓ 0-RTT finished"
