#!/usr/bin/env bash
set -euo pipefail
for b in jq bc; do command -v "$b" >/dev/null || {
  echo "❌ $b brak"; exit 1; }; done

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOST=localhost

if [[ "$(uname)" == "Darwin" ]]; then
  HOST="host.docker.internal"
  DOCKER_NET_ARGS=()
else
  DOCKER_NET_ARGS=(--network host)
fi

if [[ $# -eq 1 ]]; then
  PORTS=("$1")
else
  PORTS=(4431 4432 8443 4434 4435 11112)
fi

REQUESTS=${REQUESTS:-100}
PAYLOAD_SIZE_MB=${PAYLOAD_SIZE_MB:-1}
PAYLOAD_SIZE_BYTES=$(awk -v m="$PAYLOAD_SIZE_MB" 'BEGIN{printf "%d", m*1048576}')
CONCURRENCY=${CONCURRENCY:-1}

echo "==== Bulk throughput TLS (${PAYLOAD_SIZE_MB}MB, c=${CONCURRENCY}, Consistent Docker) ===="
echo "Using consistent Docker OpenSSL methodology for all ports"
mkdir -p results/raw

measure() {
  local host=$1 port=$2
  local cmd_hdr="printf 'POST /upload HTTP/1.1\\r\\nHost: %s\\r\\nContent-Length: %d\\r\\nConnection: close\\r\\n\\r\\n' $HOST ${PAYLOAD_SIZE_BYTES}; head -c ${PAYLOAD_SIZE_BYTES} /dev/zero"
  case $port in
    4431)
      docker exec -e OPENSSL_ia32cap="${OPENSSL_ia32cap:-}" tls-perf-nginx sh -lc "time -p sh -c \"( ${cmd_hdr} ) | /usr/local/bin/openssl s_client -quiet -provider default -tls1_3 -CAfile /etc/nginx/certs/ca.pem -connect ${host}:4431 >/dev/null 2>&1\" 2>&1 | grep real | awk '{print \$2}'"
      ;;
    4432)
      docker exec -e OPENSSL_ia32cap="${OPENSSL_ia32cap:-}" tls-perf-nginx sh -lc "time -p sh -c \"( ${cmd_hdr} ) | /usr/local/bin/openssl s_client -quiet -provider default -tls1_3 -CAfile /etc/nginx/certs/ca.pem -connect ${host}:4432 >/dev/null 2>&1\" 2>&1 | grep real | awk '{print \$2}'"
      ;;
    8443)
      docker exec -e OPENSSL_ia32cap="${OPENSSL_ia32cap:-}" tls-perf-nginx sh -lc "time -p sh -lc \"( ${cmd_hdr} ) | /usr/local/bin/openssl s_client -quiet -provider default -provider oqsprovider -groups X25519MLKEM768 -tls1_3 -CAfile /etc/nginx/certs/ca.pem -connect ${host}:8443 >/dev/null 2>&1\" 2>&1 | grep real | awk '{print \$2}'"
      ;;
    4434)
      docker exec -e OPENSSL_ia32cap="${OPENSSL_ia32cap:-}" tls-perf-nginx sh -lc "time -p sh -c \"( ${cmd_hdr} ) | /usr/local/bin/openssl s_client -quiet -provider default -tls1_3 -CAfile /etc/nginx/certs/ca.pem -connect ${host}:4434 >/dev/null 2>&1\" 2>&1 | grep real | awk '{print \$2}'"
      ;;
    4435)
      docker exec -e OPENSSL_ia32cap="${OPENSSL_ia32cap:-}" tls-perf-nginx sh -lc "time -p sh -c \"( ${cmd_hdr} ) | /usr/local/bin/openssl s_client -quiet -provider default -tls1_3 -CAfile /etc/nginx/certs/ca.pem -connect ${host}:4435 >/dev/null 2>&1\" 2>&1 | grep real | awk '{print \$2}'"
      ;;
    11112)
      docker exec wolfssl-cli sh -lc "time -p sh -c \"( ${cmd_hdr} ) | /usr/local/bin/wolf-client -h ${host} -p 11112 -v 4 --pqc X25519_ML_KEM_768 -A /certs/ca.pem -x >/dev/null 2>&1\" 2>&1 | grep real | awk '{print \$2}'"
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
  total_req_seconds=0
  total_wall_seconds=0
  successful=0
  failed=0

  if [[ "$CONCURRENCY" -le 1 ]]; then
    # Sequential mode (original behavior)
    for i in $(seq "$REQUESTS"); do
      echo -n "  Request $i/$REQUESTS: "
      if t=$(measure "$HOST" "$PORT" 2>/dev/null); then
        if [[ -n "$t" && "$t" != "0" && "$t" != "" ]]; then
          echo "$t" >>"$raw"
          total_req_seconds=$(echo "$total_req_seconds + $t" | bc -l)
          printf "%.3fs ✅\n" "$t"
          ((successful++))
        else
          echo "FAILED (empty) ❌"
          ((failed++))
        fi
      else
        echo "FAILED (error) ❌"
        ((failed++))
      fi
    done
    total_wall_seconds=$total_req_seconds
  else
    # Parallel mode (CONCURRENCY>1)
    batches=$(( (REQUESTS + CONCURRENCY - 1) / CONCURRENCY ))
    req_left=$REQUESTS
    for b in $(seq "$batches"); do
      this_batch=$(( req_left < CONCURRENCY ? req_left : CONCURRENCY ))
      req_left=$(( req_left - this_batch ))
      echo "  Batch $b/$batches (c=$this_batch)"
      tmpdir=$(mktemp -d)
      start=$(date +%s.%N)
      pids=()
      for j in $(seq "$this_batch"); do
        (
          if t=$(measure "$HOST" "$PORT" 2>/dev/null); then
            if [[ -n "$t" && "$t" != "0" && "$t" != "" ]]; then
              echo "$t" >>"$raw"
              echo "$t" >"$tmpdir/t.$j"
              exit 0
            fi
          fi
          exit 1
        ) &
        pids+=("$!")
      done
      # Wait for batch
      batch_failed=0
      for pid in "${pids[@]}"; do
        if ! wait "$pid"; then
          ((batch_failed++))
        fi
      done
      end=$(date +%s.%N)
      batch_elapsed=$(echo "$end - $start" | bc -l)
      total_wall_seconds=$(echo "$total_wall_seconds + $batch_elapsed" | bc -l)
      # Sum successful times
      for f in "$tmpdir"/t.*; do
        if [[ -f "$f" ]]; then
          val=$(cat "$f")
          total_req_seconds=$(echo "$total_req_seconds + $val" | bc -l)
          ((successful++))
        fi
      done
      ((failed+=batch_failed))
      rm -rf "$tmpdir"
      printf "    Batch elapsed: %.3fs, success so far: %d, failed: %d\n" "$batch_elapsed" "$successful" "$failed"
    done
  fi

  if [[ $successful -eq 0 ]]; then
    echo "❌ All requests failed for port $PORT"
    continue
  fi

  avg=$(echo "scale=6; $total_req_seconds/$successful" | bc -l)
  rps=$(echo "scale=6; $successful/$total_wall_seconds" | bc -l)
  throughput_mbps=$(echo "scale=6; $successful * $PAYLOAD_SIZE_MB / $total_wall_seconds" | bc -l)

  echo "📊 Results for port $PORT:"
  echo "  * Successful: $successful/$REQUESTS requests"
  echo "  * Avg time (per-req): ${avg}s"
  echo "  * RPS (wall): ${rps}"
  echo "  * Throughput (wall): ${throughput_mbps} MB/s"

  # Enhanced JSON output with methodology info
  out="results/bulk_${PORT}_r${REQUESTS}_p${PAYLOAD_SIZE_MB}_c${CONCURRENCY}.json"
  jq -n --arg host "$HOST" --arg port "$PORT" \
        --arg rps "$rps" --arg avg "$avg" \
        --arg successful "$successful" --arg total_requests "$REQUESTS" \
        --arg failed "$failed" --arg payload "$PAYLOAD_SIZE_MB" \
        --arg throughput "$throughput_mbps" --arg concurrency "$CONCURRENCY" \
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
          concurrency: ($concurrency|tonumber),
          measurement_method: "openssl_in_nginx_container_http_post",
          algorithm: (
            if ($port|tonumber) == 4431 then "X25519_AES-GCM"
            elif ($port|tonumber) == 4432 then "X25519_ChaCha20"  
            elif ($port|tonumber) == 8443 then "X25519MLKEM768_AES-GCM"
            elif ($port|tonumber) == 4434 then "X25519_AES-GCM_wolfSSL"
            elif ($port|tonumber) == 4435 then "X25519_ChaCha20_wolfSSL"
            elif ($port|tonumber) == 11112 then "X25519_ML_KEM_768_wolfSSL"
            else "Unknown" end
          ),
          note: "HTTP POST via OpenSSL inside nginx container (wolfSSL client for 11112)"
        }' > "$out"
  cp "$out" "results/bulk_${PORT}.json"
done

echo ""; echo "✅ Consistent bulk throughput testing completed"
echo "📊 All measurements used Docker OpenSSL for fair algorithm comparison"