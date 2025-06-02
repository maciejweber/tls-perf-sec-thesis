#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOST=localhost

# jeżeli wywołane z parametrem → tylko ten port; inaczej standardowa trójka
if [[ $# -eq 1 ]]; then
  PORTS=("$1")
else
  PORTS=(4431 4432 8443)
fi

SAMPLES=10
OUTDIR="$ROOT_DIR/results"; mkdir -p "$OUTDIR"

measure() {
  local port=$1

  # ── hybryda ML-KEM (8443) — time -p w kontenerze ─────────────────────────
  if [[ $port == 8443 ]]; then
    docker run --rm --network host \
      -v "$ROOT_DIR/certs:/certs:ro" \
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
    return
  fi

  # ── klasyczne porty: curl zwraca czysty time_appconnect ──────────────────
  curl -kso /dev/null -w '%{time_appconnect}\n' "https://${HOST}:$port/"
}

echo "==== Handshake TLS (${SAMPLES} próbek) ===="
for PORT in "${PORTS[@]}"; do
  # dostępność serwera
  if [[ $PORT == 8443 ]]; then
    docker run --rm --network host -v "$ROOT_DIR/certs:/certs:ro" \
      openquantumsafe/oqs-ossl3 \
        openssl s_client -brief -verify_quiet \
          -provider default -provider oqsprovider \
          -groups X25519MLKEM768 -tls1_3 \
          -CAfile /certs/ca.pem \
          -connect "$HOST:$PORT" </dev/null >/dev/null 2>&1 || {
            echo "⚠️  $HOST:$PORT nieosiągalny – pomijam"; continue; }
  else
    curl -ksm1 "https://${HOST}:${PORT}/" >/dev/null || {
      echo "⚠️  ${HOST}:${PORT} nieosiągalny – pomijam"; continue; }
  fi

  total=0
  for _ in $(seq "$SAMPLES"); do
    total=$(echo "$total + $(measure "$PORT")" | bc -l)
  done
  mean_ms=$(echo "scale=3; 1000 * $total / $SAMPLES" | bc -l)

  printf "→ %s:%s   %.3f ms\n" "$HOST" "$PORT" "$mean_ms"
  jq -n --arg port "$PORT" --arg mean "$mean_ms" --arg smp "$SAMPLES" \
      '{port:($port|tonumber), mean_ms:($mean|tonumber), samples:($smp|tonumber)}' \
      > "$OUTDIR/handshake_${PORT}.json"
done
