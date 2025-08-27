#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

HOST=localhost
if [[ "$(uname)" == "Darwin" ]]; then
  HOST="host.docker.internal"
  export DOCKER_USE_HOST_NET="0"
else
  export DOCKER_USE_HOST_NET="1"
fi

if [[ $# -eq 1 ]]; then
  PORTS=("$1")
else
  PORTS=(4431 4432 8443)
fi

COUNT=${COUNT:-3}
EARLY_DATA_MB=${EARLY_DATA_MB:-8}
OUTDIR="$ROOT_DIR/results"; mkdir -p "$OUTDIR"

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
TEST_DIR="$OUTDIR/full_post/${NETEM_PROFILE}_${AES_TAG}_mb${EARLY_DATA_MB}_n${COUNT}"

# Clean and create test directory
rm -rf "$TEST_DIR" 2>/dev/null || true
mkdir -p "$TEST_DIR"

echo "==== Full handshake + POST (no resumption, Organized Folder Structure) ===="
echo "📁 Test directory: $TEST_DIR"
echo "🌐 NetEm profile: $NETEM_PROFILE"
echo "🔐 AES status: $AES_TAG"
echo "📦 POST size: ${EARLY_DATA_MB}MB, Count: ${COUNT}"
echo ""

time_full_post() {
  local port=$1
  python3 - "$port" "$HOST" "$EARLY_DATA_MB" <<'PY'
import sys, subprocess, time, os
port = int(sys.argv[1]); host=sys.argv[2]; mb=int(sys.argv[3])
bytes_ = mb*1048576
use_host_net = os.environ.get("DOCKER_USE_HOST_NET","1") == "1"
base=["docker","run","--rm"] + (["--network","host"] if use_host_net else []) + [
      "-e","OPENSSL_ia32cap="+os.environ.get("OPENSSL_ia32cap",""),
      "openquantumsafe/oqs-ossl3","sh","-lc"]
if port==8443:
  prov="-provider default -provider oqsprovider -groups X25519MLKEM768"
else:
  prov="-provider default"
cmd=(
  f"( printf 'POST /upload HTTP/1.1\\r\\nHost: {host}\\r\\nContent-Length: {bytes_}\\r\\nConnection: close\\r\\n\\r\\n'; "
  f"head -c {bytes_} /dev/zero ) | openssl s_client -quiet -tls1_3 {prov} -CAfile /etc/ssl/certs/ca-certificates.crt "
  f"-connect {host}:{port} >/dev/null 2>&1"
)
start=time.perf_counter(); subprocess.run(base+[cmd], check=False); el=time.perf_counter()-start
print(f"{el:.6f}")
PY
}

echo "==== Full handshake + POST (no resumption) ===="
for PORT in "${PORTS[@]}"; do
  total=0
  for _ in $(seq "$COUNT"); do
    t=$(time_full_post "$PORT")
    total=$(echo "$total + ${t:-0}" | bc -l)
  done
  avg=$(echo "scale=6; $total/$COUNT" | bc -l)
  printf "→ %s:%s  full+POST avg=%.6fs (size=%dMB)\n" "$HOST" "$PORT" "$avg" "$EARLY_DATA_MB"
  out="$TEST_DIR/fullpost_${PORT}_mb${EARLY_DATA_MB}_n${COUNT}.json"
  jq -n --arg avg "$avg" '{avg_time:($avg|tonumber), method:"full_handshake_post_host_timed"}' \
       > "$out"
  cp "$out" "$TEST_DIR/fullpost_${PORT}.json"
done

echo "✓ full POST finished" 