#!/usr/bin/env bash
# FIXED run_all.sh - Comprehensive resource measurement
set -euo pipefail

IMPLEMENTATIONS=(openssl boringssl wolfssl)
SUITES=(x25519_aesgcm chacha20 kyber_hybrid)
TESTS=(handshake bulk 0rtt)
ITERATIONS=${ITERATIONS:-30}
NETEM=${NETEM:-0}
MEASURE_RESOURCES=${MEASURE_RESOURCES:-0}

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ $MEASURE_RESOURCES -eq 1 ]]; then
  if [[ ! -x "$ROOT_DIR/scripts/measure_resources.sh" ]]; then
    echo "⚠️  scripts/measure_resources.sh nie jest wykonywalny"
    echo "   Uruchom: chmod +x scripts/measure_resources.sh"
    MEASURE_RESOURCES=0
  fi
fi

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
RUN_DIR="$ROOT_DIR/results/run_${TIMESTAMP}"
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
Implementations: ${IMPLEMENTATIONS[@]}
Suites: ${SUITES[@]}
Tests: ${TESTS[@]}
REQUESTS: ${REQUESTS:-100}
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
    package_watts) echo W;;
    cpu_cycles_per_byte) echo "cycles/byte";;
    efficiency_mb_per_joule) echo "MB/s/W";;
    crypto_throughput_mb_s) echo "MB/s";;
    crypto_operation_ms) echo ms;;
    *) echo -;;
  esac
}

pairs() {
  jq -Mr '
    to_entries
    | map(
        if   .key|test("avg_(request_)?time(_s)?") then {k:"mean_time_s",v:.value}
        elif .key=="requests_per_second"      then {k:"rps",v:.value}
        elif .key|test("^(host|port|config|successful_|total_)") then empty
        else {k:.key,v:.value} end )
    | .[] | "\(.k) \(.v)"
  ' "$1"
}

# === ENHANCED CRYPTO PERFORMANCE MEASUREMENT ===
measure_crypto_performance() {
    local suite=$1 impl=$2 run=$3
    
    if [[ $MEASURE_RESOURCES -eq 0 ]]; then
        return 0
    fi
    
    echo "  📊 Measuring crypto performance for $suite..."
    
    local cmd=""
    local test_name=""
    
    case "$suite" in
        x25519_aesgcm) 
            # Test both ECDH and AES separately
            local ecdh_cmd="docker run --rm --network host openquantumsafe/oqs-ossl3 sh -c 'openssl speed -seconds 1 ecdh'"
            local aes_cmd="docker run --rm --network host openquantumsafe/oqs-ossl3 sh -c 'openssl speed -provider default -evp aes-128-gcm -seconds 1'"
            
            # Test ECDH
            if timeout 60 "$ROOT_DIR/scripts/measure_resources.sh" "$ecdh_cmd" >/dev/null 2>&1; then
                local latest_ecdh=$(ls -t "$ROOT_DIR/results"/combined_*.json 2>/dev/null | head -1)
                if [[ -f "$latest_ecdh" ]]; then
                    cp "$latest_ecdh" "$RUN_DIR/perf_${impl}_${suite}_ecdh_run${run}.json"
                    
                    local ecdh_cycles=$(jq -r '.cpu_cycles_per_byte // 0' "$latest_ecdh")
                    local ecdh_ops=$(jq -r '.throughput_mb_s // 0' "$latest_ecdh")
                    local ecdh_watts=$(jq -r '.package_watts // 0' "$latest_ecdh")
                    
                    echo "$impl,$suite,crypto,$run,ecdh_cycles_per_byte,$ecdh_cycles,cycles/byte" >>"$CSV"
                    echo "$impl,$suite,crypto,$run,ecdh_throughput_mb_s,$ecdh_ops,MB/s" >>"$CSV"
                    echo "$impl,$suite,crypto,$run,ecdh_power_watts,$ecdh_watts,W" >>"$CSV"
                fi
            fi
            
            # Test AES
            cmd="$aes_cmd"
            test_name="aes"
            ;;
        chacha20)      
            cmd="docker run --rm --network host openquantumsafe/oqs-ossl3 sh -c 'openssl speed -provider default -evp chacha20-poly1305 -seconds 1'"
            test_name="chacha20"
            ;;
        kyber_hybrid)  
            cmd="docker run --rm --network host openquantumsafe/oqs-ossl3 sh -c 'openssl speed -provider oqsprovider -provider default -seconds 1 X25519MLKEM768'"
            test_name="kyber"
            ;;
        *)             
            return 0
            ;;
    esac
    
    if [[ -n "$cmd" ]]; then
        local perf_output="$RUN_DIR/perf_${impl}_${suite}_run${run}.txt"
        
        if timeout 60 "$ROOT_DIR/scripts/measure_resources.sh" "$cmd" >"$perf_output" 2>&1; then
            
            # Find the latest performance JSON
            local latest_perf=$(ls -t "$ROOT_DIR/results"/combined_*.json 2>/dev/null | head -1)
            if [[ -f "$latest_perf" ]]; then
                cp "$latest_perf" "$RUN_DIR/perf_${impl}_${suite}_run${run}.json"
                
                # Extract comprehensive metrics
                local mean_time=$(jq -r '.mean_time_ms // 0' "$latest_perf")
                local watts=$(jq -r '.package_watts // 0' "$latest_perf")
                local cycles_per_byte=$(jq -r '.cpu_cycles_per_byte // 0' "$latest_perf")
                local efficiency=$(jq -r '.energy_efficiency_mb_per_joule // 0' "$latest_perf")
                local throughput=$(jq -r '.throughput_mb_s // 0' "$latest_perf")
                local cpu_cycles=$(jq -r '.cpu_cycles_estimated // 0' "$latest_perf")
                local bytes_processed=$(jq -r '.bytes_processed // 0' "$latest_perf")
                
                # Add all metrics to CSV
                echo "$impl,$suite,crypto,$run,crypto_operation_ms,$mean_time,ms" >>"$CSV"
                echo "$impl,$suite,crypto,$run,package_watts,$watts,W" >>"$CSV"
                echo "$impl,$suite,crypto,$run,cpu_cycles_per_byte,$cycles_per_byte,cycles/byte" >>"$CSV"
                echo "$impl,$suite,crypto,$run,efficiency_mb_per_joule,$efficiency,MB/s/W" >>"$CSV"
                echo "$impl,$suite,crypto,$run,crypto_throughput_mb_s,$throughput,MB/s" >>"$CSV"
                echo "$impl,$suite,crypto,$run,total_cpu_cycles,$cpu_cycles,cycles" >>"$CSV"
                echo "$impl,$suite,crypto,$run,bytes_processed,$bytes_processed,bytes" >>"$CSV"
                
                echo "    ✓ ${test_name}: $throughput MB/s, $cycles_per_byte cycles/byte, $efficiency MB/s/W"
            fi
        else
            echo "    ⚠️  Crypto measurement failed for $suite"
        fi
    fi
}

run_once() {
  local impl=$1 suite=$2 test=$3 run=$4
  echo "▶ $impl/$suite/$test #$run"
  local prt json ; prt=$(port "$suite")

  case $test in
    handshake) "$ROOT_DIR/scripts/run_handshake.sh" "$prt" >/dev/null ;;
    bulk)      
      "$ROOT_DIR/scripts/run_bulk.sh" "$prt" >/dev/null
      
      # Enhanced crypto performance measurement - every 5th run for efficiency
      if [[ $MEASURE_RESOURCES -eq 1 && "$impl" == "openssl" && $(( run % 5 )) -eq 1 ]]; then
        measure_crypto_performance "$suite" "$impl" "$run"
      fi
      ;;
    0rtt) "$ROOT_DIR/scripts/run_0rtt.sh" "$prt" >/dev/null ;;
  esac

  case $test in
    handshake) json="$ROOT_DIR/results/handshake_${prt}.json" ;;
    bulk)      json="$ROOT_DIR/results/bulk_${prt}.json"      ;;
    0rtt)      json="$ROOT_DIR/results/simple_${prt}.json"    ;;
  esac
  
  [[ -f $json ]] || { echo "⚠️  brak $json"; return; }

  cp "$json" "$RUN_DIR/"

  while read -r m v; do
    echo "$impl,$suite,$test,$run,$m,$v,$(unit "$m")" >>"$CSV"
  done < <(pairs "$json")
}

export -f run_once port unit pairs

START_TIME=$(date +%s)

echo "🚀 Starting comprehensive TLS benchmark..."
echo "   Iterations: $ITERATIONS"
echo "   Resource measurement: $([[ $MEASURE_RESOURCES -eq 1 ]] && echo "Enabled" || echo "Disabled")"
echo "   Implementations: ${IMPLEMENTATIONS[*]}"
echo "   Cipher suites: ${SUITES[*]}"
echo "   Tests: ${TESTS[*]}"
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
        
        # Progress indicator every 10 tests
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

# Update config with final stats
cat >> "$RUN_DIR/config.txt" <<EOF

=== FINAL STATISTICS ===
Duration: ${DURATION_MIN}m ${DURATION_SEC}s
Total measurements: $current_test
Completed at: $(date)
EOF

if [[ -d "$ROOT_DIR/results/raw" ]]; then
  cp -r "$ROOT_DIR/results/raw" "$RUN_DIR/"
fi

# Clean up temporary files
find "$ROOT_DIR/results" -name "hf_*.json" -o -name "pm_*.txt" -o -name "combined_*.json" | \
  grep -v "$RUN_DIR" | xargs rm -f 2>/dev/null || true

ln -sfn "$RUN_DIR" "$ROOT_DIR/results/latest"

echo ""
echo "✅ Results saved in: $RUN_DIR"
echo "🔗 Latest results: results/latest"

# Generate quick summary
if [[ -f "$CSV" ]]; then
    echo ""
    echo "📈 Quick Summary:"
    total_rows=$(( $(wc -l < "$CSV") - 1 ))
    crypto_measurements=$(grep -c "crypto," "$CSV" 2>/dev/null || echo "0")
    unique_configs=$(tail -n +2 "$CSV" | cut -d, -f2 | sort -u | wc -l)
    
    echo "   Data points collected: $total_rows"
    echo "   Crypto measurements: $crypto_measurements"
    echo "   Unique configurations: $unique_configs"
    
    echo ""
    echo "🔬 Next steps:"
    echo "   1. Run analysis: python3 analyze.py"
    echo "   2. Check results: ls results/latest/"
    echo "   3. View plots: ls figures/"
fi

if [[ $NETEM -eq 1 ]]; then
  "$ROOT_DIR/scripts/netem_mac.sh" clear || true
fi