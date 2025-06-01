#!/usr/bin/env bash
set -euo pipefail
###############################################################################
# run_handshake.sh — szybki pomiar handshake TLS (TCP➜TLS) przez curl.
#   Wynik: results/handshake_<port>.json  {port, mean_ms, samples}
###############################################################################

HOST=${1:-localhost}            # serwer Nginx z docker-compose
PORTS=(4431 4432)               # AES-GCM / ChaCha20 (4433 pomijamy – Ed25519 statyczny)
SAMPLES=20                      # 20 próbek ≃ 1-2 s

OUTDIR="results"; mkdir -p "$OUTDIR"
echo "==== Handshake TLS (${SAMPLES} próbek) na ${HOST} ===="

measure() {                     # zwraca czas handshake w sekundach
  curl -k -o /dev/null -s -w '%{time_appconnect}\n' "https://${HOST}:$1/"
}

for PORT in "${PORTS[@]}"; do
  if ! curl -k -m1 -o /dev/null -s "https://${HOST}:${PORT}/" 2>/dev/null; then
    echo "⚠️  ${HOST}:${PORT} nieosiągalny – pomijam"
    continue
  fi

  total=0
  for _ in $(seq 1 "$SAMPLES"); do
    t=$(measure "$PORT")
    total=$(echo "$total + $t" | bc -l)
  done
  mean_ms=$(echo "scale=3; 1000 * $total / $SAMPLES" | bc -l)

  printf "→ %s:%s   %.3f ms\n" "$HOST" "$PORT" "$mean_ms"

  jq -n --arg port "$PORT" --arg mean "$mean_ms" --arg smp "$SAMPLES" \
    '{port:($port|tonumber), mean_ms:($mean|tonumber), samples:($smp|tonumber)}' \
    > "${OUTDIR}/handshake_${PORT}.json"
done
