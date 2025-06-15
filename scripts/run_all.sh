#!/usr/bin/env bash
set -euo pipefail

echo "🔑  requesting sudo to keep powermetrics alive..."
sudo -v
( while true; do sudo -n true; sleep 240; done ) &
SUDO_KEEP=$!
trap "kill $SUDO_KEEP 2>/dev/null" EXIT

IMPLEMENTATIONS=(openssl boringssl wolfssl)
SUITES=(x25519_aesgcm chacha20 kyber_hybrid)
TESTS=(handshake bulk 0rtt)
ITERATIONS=${ITERATIONS:-30}
NETEM=${NETEM:-0}
MEASURE_RESOURCES=${MEASURE_RESOURCES:-0}
PAYLOAD_SIZE_MB=${PAYLOAD_SIZE_MB:-1}

################################################################################
### AES-NI section – set DISABLE_AESNI=1 before running to disable the opcode ###
################################################################################
if [[ "${DISABLE_AESNI:-0}" -eq 1 ]]; then
  echo "🚫  AES-NI disabled for this benchmark (OPENSSL_ia32cap mask set)"
  export OPENSSL_ia32cap="~0x200000200000000"
  AESNI_STATUS="off"
  AESNI_SUFFIX="_aesoff"
else
  unset OPENSSL_ia32cap
  AESNI_STATUS="on"
  AESNI_SUFFIX=""
fi
################################################################################

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ $MEASURE_RESOURCES -eq 1 ]]; then
  if [[ ! -x "$ROOT_DIR/scripts/measure_resources.sh" ]]; then
    echo "⚠️  scripts/measure_resources.sh nie jest wykonywalny"
    echo "   Uruchom: chmod +x scripts/measure_resources.sh"
    MEASURE_RESOURCES=0
  fi
fi

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
RUN_DIR="$ROOT_DIR/results/run_${TIMESTAMP}${AESNI_SUFFIX}"
mkdir -p "$RUN_DIR"

if [[ $NETEM -eq 1 ]]; then
  NETEM_DELAY=${NETEM_DELAY:-50}
  NETEM_LOSS=${NETEM_LOSS:-0.01}

  echo "🌐 Włączam NetEm: delay=${NETEM_DELAY}ms loss=${NETEM_LOSS}"
  "$ROOT_DIR/scripts/netem_mac.sh" "$NETEM_DELAY" "$NETEM_LOSS"

  cat > "$RUN_DIR/netem.txt" <<EOF
NetEm Configuration:
Delay: ${NETEM_DELAY}ms
Loss: ${NETEM_LOSS}
Applied at: $(date)
EOF

  trap '"$ROOT_DIR/scripts/netem_mac.sh" clear' EXIT
fi

cat > "$RUN_DIR/config.txt" <<EOF
Timestamp: $TIMESTAMP
Date: $(date)
Iterations: $ITERATIONS
AES-NI: $AESNI_STATUS
Implementations: ${IMPLEMENTATIONS[@]}
Suites: ${SUITES[@]}
Tests: ${TESTS[@]}
REQUESTS: ${REQUESTS:-100}
PAYLOAD_SIZE_MB: $PAYLOAD_SIZE_MB
NetEm: $([[ $NETEM -eq 1 ]] && echo "Yes (delay=${NETEM_DELAY}ms, loss=${NETEM_LOSS})" || echo "No")
Resource Measurement: $([[ $MEASURE_RESOURCES -eq 1 ]] && echo "Yes" || echo "No")
EOF

echo "📁 Zapisuję wyniki w: $RUN_DIR"

CSV="$RUN_DIR/bench.csv"
echo "implementation,suite,test,run,metric,value,unit" >"$CSV"

port() {
  case $1 in
    x25519_aesgcm) echo 4431 ;;
    chacha20)      echo 4432 ;;
    kyber_hybrid)  echo 8443 ;;
  esac
}

unit() {
  case $1 in
    mean_ms) echo ms;;
    mean_time_s) echo s;;
    rps) echo "ops/s";;
    resource_mean_ms) echo ms;;
    resource_watts) echo W;;
    resource_cpu_freq_ghz) echo GHz;;
    package_watts) echo W;;
    throughput_mb_s) echo "MB/s";;
    *) echo -;;
  esac
}

pairs() {
  jq -Mr '
    to_entries
    | map(
        if   .key|test("avg_(request_)?time(_s)?") then {k:"mean_time_s",v:.value}
        elif .key=="requests_per_second"           then {k:"rps",v:.value}
        elif .key|test("^(host|port|config|successful_|total_)") then empty
        else {k:.key,v:.value} end )
    | .[] | "\(.k) \(.v)"
  ' "$1"
}

run_once() {
  local impl=$1 suite=$2 test=$3 run=$4
  echo "▶ $impl/$suite/$test #$run"
  local prt json
  prt=$(port "$suite")

  case $test in
    handshake) "$ROOT_DIR/scripts/run_handshake.sh" "$prt" >/dev/null ;;
    bulk)      "$ROOT_DIR/scripts/run_bulk.sh"       "$prt" >/dev/null ;;
    0rtt)      "$ROOT_DIR/scripts/run_0rtt.sh"       "$prt" >/dev/null ;;
  esac

  case $test in
    handshake) json="$ROOT_DIR/results/handshake_${prt}.json" ;;
    bulk)      json="$ROOT_DIR/results/bulk_${prt}.json"      ;;
    0rtt)      json="$ROOT_DIR/results/simple_${prt}.json"    ;;
  esac

  if [[ ! -f "$json" ]]; then
    echo "⚠️  brak $json"
    return
  fi

  cp "$json" "$RUN_DIR/"

  while read -r m v; do
    echo "$impl,$suite,$test,$run,$m,$v,$(unit "$m")" >>"$CSV"
  done < <(pairs "$json")

  if [[ $MEASURE_RESOURCES -eq 1 && "$test" == "bulk" && $(( run % 5 )) -eq 1 ]]; then
    echo "  📊 Measuring system resources..."
    local simple_cmd="openssl speed -evp aes-128-gcm -seconds 1"

    if "$ROOT_DIR/scripts/measure_resources.sh" "$simple_cmd" >/dev/null 2>&1; then
      local latest_resource
      latest_resource=$(ls -t "$ROOT_DIR/results"/combined_*.json 2>/dev/null | head -1)
      if [[ -f "$latest_resource" ]]; then
        cp "$latest_resource" "$RUN_DIR/resource_${impl}_${suite}_${test}_run${run}.json"

        local watts cpu_freq
        watts=$(jq -r '.package_watts // 0' "$latest_resource" 2>/dev/null)
        cpu_freq=$(jq -r '.cpu_freq_ghz // 0' "$latest_resource" 2>/dev/null)

        if [[ "$watts" != "0" && "$watts" != "null" ]]; then
          echo "$impl,$suite,$test,$run,resource_watts,$watts,W"           >>"$CSV"
          echo "$impl,$suite,$test,$run,resource_cpu_freq_ghz,$cpu_freq,GHz" >>"$CSV"
          echo "    ✓ Resources: ${watts}W, ${cpu_freq}GHz"
        fi
      fi
    fi
  fi
}

export -f run_once port unit pairs
export PAYLOAD_SIZE_MB

START_TIME=$(date +%s)

echo "🚀 Starting TLS performance benchmark..."
echo "   AES-NI:          $AESNI_STATUS"
echo "   Iterations:      $ITERATIONS"
echo "   Resource meas.:  $([[ $MEASURE_RESOURCES -eq 1 ]] && echo Enabled || echo Disabled)"
echo "   Payload size:    ${PAYLOAD_SIZE_MB}MB"
echo "   Implementations: ${IMPLEMENTATIONS[*]}"
echo "   Cipher suites:   ${SUITES[*]}"
echo "   Tests:           ${TESTS[*]}"
echo ""

total_tests=$((${#IMPLEMENTATIONS[@]} * ${#SUITES[@]} * ${#TESTS[@]} * ITERATIONS))
current_test=0

for impl in "${IMPLEMENTATIONS[@]}"; do
  echo ""
  echo "📊 Testing implementation: $impl"
  for suite in "${SUITES[@]}"; do
    echo "  🔧 Testing suite: $suite"
    for test in "${TESTS[@]}"; do
      echo "    🧪 Running test: $test"
      for run in $(seq "$ITERATIONS"); do
        current_test=$((current_test + 1))
        progress=$((current_test * 100 / total_tests))
        echo -ne "    Progress: $current_test/$total_tests ($progress%)\r"

        run_once "$impl" "$suite" "$test" "$run"

        if [[ $((current_test % 10)) -eq 0 ]]; then
          echo ""
          echo "    📈 Completed $current_test/$total_tests tests ($progress%)"
        fi
      done
      echo ""
    done
  done
done

END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))
DURATION_MIN=$((DURATION / 60))
DURATION_SEC=$((DURATION % 60))

echo ""
echo "📊 === BENCHMARK COMPLETED ==="
echo "⏱️  Duration: ${DURATION_MIN}m ${DURATION_SEC}s"
echo "📊 Total measurements: $current_test"

cat >> "$RUN_DIR/config.txt" <<EOF

=== FINAL STATISTICS ===
Duration: ${DURATION_MIN}m ${DURATION_SEC}s
Total measurements: $current_test
Completed at: $(date)
EOF

if [[ -d "$ROOT_DIR/results/raw" ]]; then
  cp -r "$ROOT_DIR/results/raw" "$RUN_DIR/"
fi

find "$ROOT_DIR/results" -name "hf_*.json" -o -name "pm_*.txt" -o -name "combined_*.json" \
  | grep -v "$RUN_DIR" | xargs rm -f 2>/dev/null || true

ln -sfn "$RUN_DIR" "$ROOT_DIR/results/latest"

echo ""
echo "✅ Results saved in: $RUN_DIR"
echo "🔗 Latest results:  results/latest"

if [[ -f "$CSV" ]]; then
  rows=$(wc -l < "$CSV")
  total_rows=$(( rows - 1 ))
  unique_configs=$(tail -n +2 "$CSV" | cut -d, -f2 | sort -u | wc -l)

  echo ""
  echo "📈 Quick Summary:"
  echo "   Data points collected: $total_rows"
  echo "   Unique configurations: $unique_configs"
fi

if [[ $NETEM -eq 1 ]]; then
  "$ROOT_DIR/scripts/netem_mac.sh" clear || true
fi
