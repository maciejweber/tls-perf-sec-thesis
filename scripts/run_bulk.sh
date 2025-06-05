#!/usr/bin/env bash
set -euo pipefail
for b in jq bc; do command -v "$b" >/dev/null || {
  echo "❌ $b brak"; exit 1; }; done

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOST=localhost

if [[ $# -eq 1 ]]; then
  PORTS=("$1")
else
  PORTS=(4431 4432 8443)
fi

REQUESTS=${REQUESTS:-100}
PAYLOAD_SIZE_MB=${PAYLOAD_SIZE_MB:-1}
PAYLOAD_SIZE_KB=$((PAYLOAD_SIZE_MB * 1024))

echo "==== Bulk throughput TLS (${PAYLOAD_SIZE_MB}MB, Consistent Docker) ===="
echo "Using consistent Docker OpenSSL methodology for all ports"
mkdir -p results/raw

# FIXED: Use consistent Docker OpenSSL approach for ALL ports
measure() {
  local host=$1 port=$2

  case $port in
    4431)
      # X25519 + AES-GCM via Docker OpenSSL
      docker run --rm --network host -v "$ROOT_DIR/certs:/certs:ro" \
        openquantumsafe/oqs-ossl3 \
          sh -c "
            time -p sh -c \"
              dd if=/dev/zero bs=1024 count=$PAYLOAD_SIZE_KB 2>/dev/null | \\
              openssl s_client -quiet \\
                -provider default \\
                -tls1_3 \\
                -CAfile /certs/ca.pem \\
                -connect localhost:4431 >/dev/null 2>&1
            \" 2>&1 | grep real | awk \"{print \\\$2}\"
          "
      ;;
    4432)
      # X25519 + ChaCha20 via Docker OpenSSL
      docker run --rm --network host -v "$ROOT_DIR/certs:/certs:ro" \
        openquantumsafe/oqs-ossl3 \
          sh -c "
            time -p sh -c \"
              dd if=/dev/zero bs=1024 count=$PAYLOAD_SIZE_KB 2>/dev/null | \\
              openssl s_client -quiet \\
                -provider default \\
                -tls1_3 \\
                -CAfile /certs/ca.pem \\
                -connect localhost:4432 >/dev/null 2>&1
            \" 2>&1 | grep real | awk \"{print \\\$2}\"
          "
      ;;
    8443)
      # X25519MLKEM768 + AES-GCM via Docker OpenSSL (original working)
      docker run --rm --network host -v "$ROOT_DIR/certs:/certs:ro" \
        openquantumsafe/oqs-ossl3 \
          sh -c "
            time -p sh -c \"
              dd if=/dev/zero bs=1024 count=$PAYLOAD_SIZE_KB 2>/dev/null | \\
              openssl s_client -quiet \\
                -provider default -provider oqsprovider \\
                -groups X25519MLKEM768 -tls1_3 \\
                -CAfile /certs/ca.pem \\
                -connect localhost:8443 >/dev/null 2>&1
            \" 2>&1 | grep real | awk \"{print \\\$2}\"
          "
      ;;
    *)
      echo "Unknown port: $port" >&2
      return 1
      ;;
  esac
}

for PORT in "${PORTS[@]}"; do
  echo ""; echo ">> Testing ${HOST}:${PORT} (Docker OpenSSL)"
  raw="results/raw/bulk_${PORT}.txt"; : >"$raw"
  total=0
  failed=0

  for i in $(seq "$REQUESTS"); do
    echo -n "  Request $i/$REQUESTS: "
    
    if t=$(measure "$HOST" "$PORT" 2>/dev/null); then
      if [[ -n "$t" && "$t" != "0" && "$t" != "" ]]; then
        echo "$t" >>"$raw"
        total=$(echo "$total + $t" | bc -l)
        printf "%.3fs ✅\n" "$t"
      else
        echo "FAILED (empty) ❌"
        ((failed++))
      fi
    else
      echo "FAILED (error) ❌"
      ((failed++))
    fi
  done

  successful=$((REQUESTS - failed))
  
  if [[ $successful -eq 0 ]]; then
    echo "❌ All requests failed for port $PORT"
    continue
  fi

  avg=$(echo "scale=6; $total/$successful" | bc -l)
  rps=$(echo "scale=2; $successful/$total" | bc -l)
  throughput_mbps=$(echo "scale=2; $successful * $PAYLOAD_SIZE_MB / $total" | bc -l)

  echo "📊 Results for port $PORT:"
  echo "  * Successful: $successful/$REQUESTS requests"
  echo "  * Avg time: ${avg}s"
  echo "  * RPS: ${rps}"
  echo "  * Throughput: ${throughput_mbps} MB/s"

  # Enhanced JSON output with methodology info
  jq -n --arg host "$HOST" --arg port "$PORT" \
        --arg rps "$rps" --arg avg "$avg" \
        --arg successful "$successful" --arg total_requests "$REQUESTS" \
        --arg failed "$failed" --arg payload "$PAYLOAD_SIZE_MB" \
        --arg throughput "$throughput_mbps" \
        '{
          host: $host, 
          port: ($port|tonumber),
          requests_per_second: ($rps|tonumber),
          avg_request_time_s: ($avg|tonumber),
          successful_requests: ($successful|tonumber),
          total_requests: ($total_requests|tonumber),
          failed_requests: ($failed|tonumber),
          payload_size_mb: ($payload|tonumber),
          throughput_mb_s: ($throughput|tonumber),
          measurement_method: "docker_openssl_consistent",
          algorithm: (
            if ($port|tonumber) == 4431 then "X25519_AES-GCM"
            elif ($port|tonumber) == 4432 then "X25519_ChaCha20"  
            elif ($port|tonumber) == 8443 then "X25519MLKEM768_AES-GCM"
            else "Unknown" end
          ),
          note: "Consistent Docker OpenSSL methodology for fair comparison"
        }' > "results/bulk_${PORT}.json"
done

echo ""; echo "✅ Consistent bulk throughput testing completed"
echo "📊 All measurements used Docker OpenSSL for fair algorithm comparison"