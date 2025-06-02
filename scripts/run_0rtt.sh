#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

HOST=localhost
if [[ $# -eq 1 ]]; then
  PORTS=("$1")
else
  PORTS=(4431 4432 8443)
fi

COUNT=5
OUTDIR="$ROOT_DIR/results"; mkdir -p "$OUTDIR"

measure () {
  local port=$1

  if [[ $port == 8443 ]]; then
    # Używamy tej samej metody co w handshake - tylko połączenie
    docker run --rm --network host -v "$ROOT_DIR/certs:/certs:ro" \
      openquantumsafe/oqs-ossl3 \
        sh -c '
          time -p sh -c "
            openssl s_client -brief \
              -provider default -provider oqsprovider \
              -groups X25519MLKEM768 -tls1_3 \
              -CAfile /certs/ca.pem \
              -connect localhost:8443 </dev/null >/dev/null 2>&1
          " 2>&1 | grep real | awk "{print \$2}"
        '
  else
    curl -kso /dev/null -w '%{time_total}\n' "https://${HOST}:${port}/"
  fi
}

echo "==== 0-RTT / prosty test TLS ===="
for PORT in "${PORTS[@]}"; do
  total=0
  for _ in $(seq "$COUNT"); do
    total=$(echo "$total + $(measure "$PORT")" | bc -l)
  done
  avg=$(echo "scale=6; $total/$COUNT" | bc -l)
  printf "→ %s:%s  avg=%.6fs\n" "$HOST" "$PORT" "$avg"

  jq -n --arg avg "$avg" '{avg_time:($avg|tonumber)}' \
       > "$OUTDIR/simple_${PORT}.json"
done

echo "✓ 0-RTT finished"
