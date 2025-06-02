#!/usr/bin/env bash
set -euo pipefail
for b in curl jq bc; do command -v "$b" >/dev/null || {
  echo "❌ $b brak"; exit 1; }; done

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOST=localhost

if [[ $# -eq 1 ]]; then
  PORTS=("$1")
else
  PORTS=(4431 4432 8443)
fi

REQUESTS=${REQUESTS:-100}   # dla 8443 – jedna paczka 1 MiB = jeden „request”

echo "==== Bulk throughput TLS ===="
mkdir -p results/raw

measure() {
  local host=$1 port=$2

  if [[ $port == 8443 ]]; then               # ML-KEM hybrid
    # Mierz czas transferu 1MB przez time -p
    docker run --rm --network host -v "$ROOT_DIR/certs:/certs:ro" \
      openquantumsafe/oqs-ossl3 \
        sh -c '
          time -p sh -c "
            dd if=/dev/zero bs=1024 count=1024 2>/dev/null | \
            openssl s_client -quiet \
              -provider default -provider oqsprovider \
              -groups X25519MLKEM768 -tls1_3 \
              -CAfile /certs/ca.pem \
              -connect localhost:8443 >/dev/null 2>&1
          " 2>&1 | grep real | awk "{print \$2}"
        '
  else                                       # klasyczne porty
    curl -kso /dev/null -w '%{time_total}\n' "https://${host}:${port}/"
  fi
}

for PORT in "${PORTS[@]}"; do
  echo ""; echo ">> ${HOST}:${PORT}"
  raw="results/raw/bulk_${PORT}.txt"; : >"$raw"
  total=0

  for _ in $(seq "$REQUESTS"); do
    t=$(measure "$HOST" "$PORT"); echo "$t" >>"$raw"
    total=$(echo "$total + $t" | bc -l)
  done

  avg=$(echo "scale=6; $total/$REQUESTS" | bc -l)
  rps=$(echo "scale=2; $REQUESTS/$total" | bc -l)
  

  jq -n --arg host "$HOST" --arg port "$PORT" \
        --arg rps "$rps" --arg avg "$avg" --arg req "$REQUESTS" \
        '{host:$host, port:($port|tonumber),
          requests_per_second:($rps|tonumber),
          avg_request_time_s:($avg|tonumber),
          total_requests:($req|tonumber)}' \
        > "results/bulk_${PORT}.json"

  echo "* avg=${avg}s   * RPS=${rps}"
done

echo ""; echo "✓ Throughput finished"
