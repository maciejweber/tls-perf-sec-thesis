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

time_full_post() {
  local port=$1
  python3 - "$port" "$HOST" "$EARLY_DATA_MB" <<'PY'
import sys, subprocess, time, os
port = int(sys.argv[1]); host=sys.argv[2]; mb=int(sys.argv[3])
bytes_ = mb*1048576
use_host_net = os.environ.get("DOCKER_USE_HOST_NET","1") == "1"
base=["docker","run","--rm"] + (["--network","host"] if use_host_net else []) + [
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
  out="$OUTDIR/fullpost_${PORT}_mb${EARLY_DATA_MB}_n${COUNT}.json"
  jq -n --arg avg "$avg" '{avg_time:($avg|tonumber), method:"full_handshake_post_host_timed"}' \
       > "$out"
  cp "$out" "$OUTDIR/fullpost_${PORT}.json"
done

echo "✓ full POST finished" 