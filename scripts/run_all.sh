#!/usr/bin/env bash
set -euo pipefail

# Allow env overrides for flexibility
IMPLEMENTATIONS=(${IMPLEMENTATIONS:-openssl wolfssl})
SUITES=(${SUITES:-x25519_aesgcm chacha20 kyber_hybrid})
TESTS=(${TESTS:-handshake bulk 0rtt})
ITERATIONS=${ITERATIONS:-30}
NETEM=${NETEM:-0}
MEASURE_RESOURCES=${MEASURE_RESOURCES:-0}
PAYLOAD_SIZE_MB=${PAYLOAD_SIZE_MB:-1}
CONCURRENCY=${CONCURRENCY:-1}

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
CONCURRENCY: $CONCURRENCY
NetEm: $([[ $NETEM -eq 1 ]] && echo "Yes (delay=${NETEM_DELAY}ms, loss=${NETEM_LOSS})" || echo "No")
Resource Measurement: $([[ $MEASURE_RESOURCES -eq 1 ]] && echo "Yes" || echo "No")
EOF

echo "📁 Zapisuję wyniki w: $RUN_DIR"

CSV="$RUN_DIR/bench.csv"
echo "implementation,suite,test,run,metric,value,unit" >"$CSV"

port() {
  local impl=$1 suite=$2
  if   [[ $impl == openssl && $suite == x25519_aesgcm ]]; then echo 4431
  elif [[ $impl == openssl && $suite == chacha20      ]]; then echo 4432
  elif [[ $impl == openssl && $suite == kyber_hybrid  ]]; then echo 8443
  elif [[ $impl == wolfssl  && $suite == x25519_aesgcm ]]; then echo 4434
  elif [[ $impl == wolfssl  && $suite == chacha20      ]]; then echo 4435
  elif [[ $impl == wolfssl  && $suite == kyber_hybrid  ]]; then echo 11112
  else echo ""; fi
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
    avg_time_s) echo s;;
    ttfb_s) echo s;;
    *) echo -;;
  esac
}

pairs() {
  jq -Mr '
    to_entries
    | map(
        if   .key|test("avg_(request_)?time(_s)?") then {k:"mean_time_s",v:.value}
        elif .key=="requests_per_second"           then {k:"rps",v:.value}
        elif .key|test("^(host|port|config|successful_|total_|concurrency|note|measurement_|algorithm|payload_|throughput_|method)") then empty
        elif .key=="ttfb_s"                         then {k:"ttfb_s",v:.value}
        elif .key=="avg_time"                       then {k:"avg_time_s",v:.value}
        else {k:.key,v:.value} end )
    | .[] | "\(.k) \(.v)"
  ' "$1"
}

run_once() {
  local impl=$1 suite=$2 test=$3 run=$4
  echo "▶ $impl/$suite/$test #$run"
  local prt json
  prt=$(port "$impl" "$suite")

  if [[ -z "$prt" ]]; then
    echo "  ⏭️  Skipping unsupported combo ($impl/$suite)"
    return
  fi

  # Skip 0-RTT for wolfssl
  if [[ "$impl" == "wolfssl" && "$test" == "0rtt" ]]; then
    echo "  ⏭️  Skipping 0-RTT for wolfssl"
    return
  fi

  case $test in
    handshake) 
      "$ROOT_DIR/scripts/run_handshake.sh" "$prt" >/dev/null
      # Try to find results in new organized folders first
      json=""
      if [[ -f "$ROOT_DIR/results/handshake/baseline_aes_on_s33/handshake_${prt}.json" ]]; then
        json="$ROOT_DIR/results/handshake/baseline_aes_on_s33/handshake_${prt}.json"
      elif [[ -f "$ROOT_DIR/results/handshake/delay_50ms_aes_on_s33/handshake_${prt}.json" ]]; then
        json="$ROOT_DIR/results/handshake/delay_50ms_aes_on_s33/handshake_${prt}.json"
      elif [[ -f "$ROOT_DIR/results/handshake/delay_50ms_loss_0.5_aes_on_s33/handshake_${prt}.json" ]]; then
        json="$ROOT_DIR/results/handshake/delay_50ms_loss_0.5_aes_on_s33/handshake_${prt}.json"
      elif [[ -f "$ROOT_DIR/results/handshake/delay_100ms_aes_on_s33/handshake_${prt}.json" ]]; then
        json="$ROOT_DIR/results/handshake/delay_100ms_aes_on_s33/handshake_${prt}.json"
      fi
      ;;
    bulk)      
      "$ROOT_DIR/scripts/run_bulk.sh" "$prt" >/dev/null
      # Try to find results in new organized folders first
      json=""
      if [[ -f "$ROOT_DIR/results/bulk/baseline_aes_on_r64_p${PAYLOAD_SIZE_MB}_c${CONCURRENCY}/bulk_${prt}.json" ]]; then
        json="$ROOT_DIR/results/bulk/baseline_aes_on_r64_p${PAYLOAD_SIZE_MB}_c${CONCURRENCY}/bulk_${prt}.json"
      elif [[ -f "$ROOT_DIR/results/bulk/delay_50ms_aes_on_r64_p${PAYLOAD_SIZE_MB}_c${CONCURRENCY}/bulk_${prt}.json" ]]; then
        json="$ROOT_DIR/results/bulk/delay_50ms_aes_on_r64_p${PAYLOAD_SIZE_MB}_c${CONCURRENCY}/bulk_${prt}.json"
      elif [[ -f "$ROOT_DIR/results/bulk/delay_50ms_loss_0.5_aes_on_r64_p${PAYLOAD_SIZE_MB}_c${CONCURRENCY}/bulk_${prt}.json" ]]; then
        json="$ROOT_DIR/results/bulk/delay_50ms_loss_0.5_aes_on_r64_p${PAYLOAD_SIZE_MB}_c${CONCURRENCY}/bulk_${prt}.json"
      elif [[ -f "$ROOT_DIR/results/bulk/delay_100ms_aes_on_r64_p${PAYLOAD_SIZE_MB}_c${CONCURRENCY}/bulk_${prt}.json" ]]; then
        json="$ROOT_DIR/results/bulk/delay_100ms_aes_on_r64_p${PAYLOAD_SIZE_MB}_c${CONCURRENCY}/bulk_${prt}.json"
      fi
      ;;
    0rtt)      
      "$ROOT_DIR/scripts/run_0rtt.sh" "$prt" >/dev/null
      # Try to find results in new organized folders first
      json=""
      if [[ -f "$ROOT_DIR/results/0rtt/baseline_aes_on_ed4_n5/simple_${prt}.json" ]]; then
        json="$ROOT_DIR/results/0rtt/baseline_aes_on_ed4_n5/simple_${prt}.json"
      elif [[ -f "$ROOT_DIR/results/0rtt/delay_50ms_aes_on_ed4_n5/simple_${prt}.json" ]]; then
        json="$ROOT_DIR/results/0rtt/delay_50ms_aes_on_ed4_n5/simple_${prt}.json"
      elif [[ -f "$ROOT_DIR/results/0rtt/delay_50ms_loss_0.5_aes_on_ed4_n5/simple_${prt}.json" ]]; then
        json="$ROOT_DIR/results/0rtt/delay_50ms_loss_0.5_aes_on_ed4_n5/simple_${prt}.json"
      elif [[ -f "$ROOT_DIR/results/0rtt/delay_100ms_aes_on_ed4_n5/simple_${prt}.json" ]]; then
        json="$ROOT_DIR/results/0rtt/delay_100ms_aes_on_ed4_n5/simple_${prt}.json"
      fi
      ;;
    ttfb)      
      "$ROOT_DIR/scripts/run_ttfb.sh" "$prt" >/dev/null || true
      # Try to find results in new organized folders first
      json=""
      if [[ -f "$ROOT_DIR/results/ttfb/baseline_kb16/ttfb_${prt}.json" ]]; then
        json="$ROOT_DIR/results/ttfb/baseline_kb16/ttfb_${prt}.json"
      elif [[ -f "$ROOT_DIR/results/ttfb/delay_50ms_kb16/ttfb_${prt}.json" ]]; then
        json="$ROOT_DIR/results/ttfb/delay_50ms_kb16/ttfb_${prt}.json"
      elif [[ -f "$ROOT_DIR/results/ttfb/delay_50ms_loss_0.5_kb16/ttfb_${prt}.json" ]]; then
        json="$ROOT_DIR/results/ttfb/delay_50ms_loss_0.5_kb16/ttfb_${prt}.json"
      elif [[ -f "$ROOT_DIR/results/ttfb/delay_100ms_kb16/ttfb_${prt}.json" ]]; then
        json="$ROOT_DIR/results/ttfb/delay_100ms_kb16/ttfb_${prt}.json"
      fi
      ;;
  esac

  if [[ -z "$json" || ! -f "$json" ]]; then
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
export CONCURRENCY

START_TIME=$(date +%s)

echo "🚀 Starting TLS performance benchmark..."
echo "   AES-NI:          $AESNI_STATUS"
echo "   Iterations:      $ITERATIONS"
echo "   Resource meas.:  $([[ $MEASURE_RESOURCES -eq 1 ]] && echo Enabled || echo Disabled)"
echo "   Payload size:    ${PAYLOAD_SIZE_MB}MB"
echo "   Concurrency:     ${CONCURRENCY}"
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
