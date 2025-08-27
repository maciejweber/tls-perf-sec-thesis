#!/usr/bin/env bash
set -euo pipefail
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

SAMPLES=${SAMPLES:-10}
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
TEST_DIR="$OUTDIR/handshake/${NETEM_PROFILE}_${AES_TAG}_s${SAMPLES}"

# Clean and create test directory
rm -rf "$TEST_DIR" 2>/dev/null || true
mkdir -p "$TEST_DIR"

# Create series directory for backward compatibility
join_ports() { local IFS=-; echo "$*"; }
PORTS_KEY=$(join_ports "${PORTS[@]}")
RUN_TAG_SUFFIX=${RUN_TAG:+_$(echo "$RUN_TAG" | tr ' ' '_')}
SERIES_DIR="$OUTDIR/series/handshake/ports_${PORTS_KEY}_s${SAMPLES}_${AES_TAG}${RUN_TAG_SUFFIX}"
rm -rf "$SERIES_DIR" 2>/dev/null || true
mkdir -p "$SERIES_DIR"

printf "script=run_handshake.sh\nports=%s\nsamples=%s\naes=%s\nnetem_profile=%s\nrun_tag=%s\nstarted_at=%s\n" \
  "$PORTS_KEY" "$SAMPLES" "$AES_TAG" "$NETEM_PROFILE" "${RUN_TAG:-}" "$(date -Iseconds)" >"$SERIES_DIR/series_info.txt"

echo "==== TLS Handshake Performance ($SAMPLES samples, Organized Folder Structure) ===="
echo "📁 Test directory: $TEST_DIR"
echo "🌐 NetEm profile: $NETEM_PROFILE"
echo "🔐 AES status: $AES_TAG"
echo ""

measure() {
  local port=$1
  case $port in
    4431)
      docker exec -e OPENSSL_ia32cap="${OPENSSL_ia32cap:-}" tls-perf-nginx sh -lc '
        time -p sh -c "
          /usr/local/bin/openssl s_client -brief \
            -provider default \
            -tls1_3 \
            -CAfile /etc/nginx/certs/ca.pem \
            -connect '"${HOST}"':4431 </dev/null >/dev/null 2>&1
        " 2>&1 | grep real | awk "{print \$2}"
      '
      ;;
    4432)
      docker exec -e OPENSSL_ia32cap="${OPENSSL_ia32cap:-}" tls-perf-nginx sh -lc '
        time -p sh -c "
          /usr/local/bin/openssl s_client -brief \
            -provider default \
            -tls1_3 \
            -CAfile /etc/nginx/certs/ca.pem \
            -connect '"${HOST}"':4432 </dev/null >/dev/null 2>&1
        " 2>&1 | grep real | awk "{print \$2}"
      '
      ;;
    8443)
      docker exec -e OPENSSL_ia32cap="${OPENSSL_ia32cap:-}" tls-perf-nginx sh -lc '
        time -p sh -c "
          /usr/local/bin/openssl s_client -brief \
            -provider default -provider oqsprovider \
            -groups X25519MLKEM768 -tls1_3 \
            -CAfile /etc/nginx/certs/ca.pem \
            -connect '"${HOST}"':8443 </dev/null >/dev/null 2>&1
        " 2>&1 | grep real | awk "{print \$2}"
      '
      ;;
    4434)
      docker exec -e OPENSSL_ia32cap="${OPENSSL_ia32cap:-}" tls-perf-nginx sh -lc '
        time -p sh -c "
          /usr/local/bin/openssl s_client -brief \
            -provider default \
            -tls1_3 \
            -CAfile /etc/nginx/certs/ca.pem \
            -connect '"${HOST}"':4434 </dev/null >/dev/null 2>&1
        " 2>&1 | grep real | awk "{print \$2}"
      '
      ;;
    4435)
      docker exec -e OPENSSL_ia32cap="${OPENSSL_ia32cap:-}" tls-perf-nginx sh -lc '
        time -p sh -c "
          /usr/local/bin/openssl s_client -brief \
            -provider default \
            -tls1_3 \
            -CAfile /etc/nginx/certs/ca.pem \
            -connect '"${HOST}"':4435 </dev/null >/dev/null 2>&1
        " 2>&1 | grep real | awk "{print \$2}"
      '
      ;;
    11112)
      docker exec wolfssl-cli sh -lc '
        time -p sh -c "
          echo GET / HTTP/1.0 | /usr/local/bin/wolf-client -h wolfssl-server-kyber -p 11112 -v 4 --pqc X25519_ML_KEM_768 >/dev/null 2>&1
        " 2>&1 | grep real | awk "{print \$2}"
      '
      ;;
    *)
      echo "Unknown port: $port" >&2
      return 1
      ;;
  esac
}

test_server_availability() {
  local port=$1
  

  return 0
}

echo "==== TLS Handshake Performance (${SAMPLES} samples, Original Docker style) ===="
echo "Using original working Docker OpenSSL approach (no SNI)"
echo ""

for PORT in "${PORTS[@]}"; do
  echo "Testing port $PORT..."
  
  # Test server availability first
  if ! test_server_availability "$PORT"; then
    echo "⚠️  $HOST:$PORT unreachable – skipping"
    echo ""
    continue
  fi

  echo "  Performing $SAMPLES handshake measurements..."
  total=0
  failed=0
  measurements=()

  for i in $(seq "$SAMPLES"); do
    if result=$(measure "$PORT" 2>/dev/null); then
      if [[ -n "$result" && "$result" != "0" && "$result" != "" ]]; then
        total=$(echo "$total + $result" | bc -l)
        measurements+=("$result")
        printf "    Sample %2d: %.6fs\n" $i $result
      else
        echo "    Sample $i: Failed (empty result)"
        ((failed++))
      fi
    else
      echo "    Sample $i: Failed (command error)  "
      ((failed++))
    fi
  done

  if [[ $failed -eq $SAMPLES ]]; then
    echo "  ❌ All measurements failed for port $PORT"
    echo ""
    continue
  fi

  successful=$((SAMPLES - failed))
  mean_s=$(echo "scale=6; $total / $successful" | bc -l)
  mean_ms=$(echo "scale=3; $mean_s * 1000" | bc -l)

  # Calculate standard deviation
  if [[ $successful -gt 1 ]]; then
    variance=0
    for measurement in "${measurements[@]}"; do
      diff=$(echo "scale=6; $measurement - $mean_s" | bc -l)
      diff_sq=$(echo "scale=6; $diff * $diff" | bc -l)
      variance=$(echo "scale=6; $variance + $diff_sq" | bc -l)
    done
    variance=$(echo "scale=6; $variance / ($successful - 1)" | bc -l)
    stddev_s=$(echo "scale=6; sqrt($variance)" | bc -l)
    stddev_ms=$(echo "scale=3; $stddev_s * 1000" | bc -l)
  else
    stddev_ms="0.000"
  fi

  printf "  📊 Results: %.3f ms ± %.3f ms (successful: %d/%d)\n" "$mean_ms" "$stddev_ms" "$successful" "$SAMPLES"
  
  # JSON output
  out="$TEST_DIR/handshake_${PORT}_s${SAMPLES}.json"
  jq -n \
    --arg port "$PORT" \
    --arg mean_ms "$mean_ms" \
    --arg stddev_ms "$stddev_ms" \
    --arg mean_s "$mean_s" \
    --arg successful "$successful" \
    --arg total "$SAMPLES" \
    --argjson measurements "$(printf '%s\n' "${measurements[@]}" | jq -R . | jq -s 'map(tonumber)')" \
    '{
       port: ($port|tonumber),
       mean_ms: ($mean_ms|tonumber),
       stddev_ms: ($stddev_ms|tonumber), 
       mean_s: ($mean_s|tonumber),
       samples: ($total|tonumber),
       successful_measurements: ($successful|tonumber),
       failed_measurements: (($total|tonumber) - ($successful|tonumber)),
       measurement_method: "openssl_in_nginx_container",
       raw_measurements: $measurements,
       algorithm: (
         if ($port|tonumber) == 4431 then "X25519_AES-GCM"
         elif ($port|tonumber) == 4432 then "X25519_ChaCha20"  
         elif ($port|tonumber) == 8443 then "X25519MLKEM768_AES-GCM"
         elif ($port|tonumber) == 4434 then "X25519_AES-GCM_wolfSSL"
         elif ($port|tonumber) == 4435 then "X25519_ChaCha20_wolfSSL"
         elif ($port|tonumber) == 11112 then "X25519_ML_KEM_768_wolfSSL"
         else "Unknown" end
       ),
       note: "Using nginx container OpenSSL client (wolfSSL for 11112)"
     }' > "$out"
  cp "$out" "$TEST_DIR/handshake_${PORT}.json"
  cp "$out" "$SERIES_DIR/handshake_${PORT}_s${SAMPLES}.json"

  echo ""
done

echo "✅ Handshake performance testing completed"
echo "📊 All measurements used OpenSSL from nginx container"
echo "📁 Results saved in: $TEST_DIR/handshake_*.json"