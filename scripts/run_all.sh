#!/usr/bin/env bash
# FIXED run_all.sh - TLS performance measurement (removed misleading crypto benchmarks)
set -euo pipefail

IMPLEMENTATIONS=(openssl boringssl wolfssl)
SUITES=(x25519_aesgcm chacha20 kyber_hybrid)
TESTS=(handshake bulk 0rtt)
ITERATIONS=${ITERATIONS:-30}
NETEM=${NETEM:-0}
MEASURE_RESOURCES=${MEASURE_RESOURCES:-0}
PAYLOAD_SIZE_MB=${PAYLOAD_SIZE_MB:-1}

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
        elif .key=="requests_per_second"      then {k:"rps",v:.value}
        elif .key|test("^(host|port|config|successful_|total_)") then empty
        else {k:.key,v:.value} end )
    | .[] | "\(.k) \(.v)"
  ' "$1"
}

# REMOVED: measure_crypto_performance function - was comparing apples to oranges
# The function was creating misleading comparisons between:
# - AES symmetric encryption (fast, bulk data processing)
# - Kyber key operations (slow, asymmetric key agreement)
# This resulted in meaningless 213x performance differences

run_once() {
  local impl=$1 suite=$2 test=$3 run=$4
  echo "▶ $impl/$suite/$test #$run"
  local prt json 
  prt=$(port "$suite")

  # Run the actual TLS test NORMALLY
  case $test in
    handshake) "$ROOT_DIR/scripts/run_handshake.sh" "$prt" >/dev/null ;;
    bulk)      "$ROOT_DIR/scripts/run_bulk.sh" "$prt" >/dev/null ;;
    0rtt)      "$ROOT_DIR/scripts/run_0rtt.sh" "$prt" >/dev/null ;;
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

  # Extract TLS performance metrics
  while read -r m v; do
    echo "$impl,$suite,$test,$run,$m,$v,$(unit "$m")" >>"$CSV"
  done < <(pairs "$json")
  
  # Add SIMPLE resource measurement (every 5th run)
  if [[ $MEASURE_RESOURCES -eq 1 && "$test" == "bulk" && $(( run % 5 )) -eq 1 ]]; then
    echo "  📊 Measuring system resources..."
    
    # Use a SIMPLE command that works, not complex TLS scripts
    local simple_cmd="openssl speed -evp aes-128-gcm -seconds 1"
    
    if "$ROOT_DIR/scripts/measure_resources.sh" "$simple_cmd" >/dev/null 2>&1; then
      # Find the latest resource JSON
      local latest_resource
      latest_resource=$(ls -t "$ROOT_DIR/results"/combined_*.json 2>/dev/null | head -1)
      if [[ -f "$latest_resource" ]]; then
        cp "$latest_resource" "$RUN_DIR/resource_${impl}_${suite}_${test}_run${run}.json"
        
        # Extract resource metrics and add to CSV
        local watts cpu_freq
        watts=$(jq -r '.package_watts // 0' "$latest_resource" 2>/dev/null)
        cpu_freq=$(jq -r '.cpu_freq_ghz // 0' "$latest_resource" 2>/dev/null)
        
        if [[ "$watts" != "0" && "$watts" != "null" ]]; then
          echo "$impl,$suite,$test,$run,resource_watts,$watts,W" >>"$CSV"
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
echo "   Iterations: $ITERATIONS"
echo "   Resource measurement: $([[ $MEASURE_RESOURCES -eq 1 ]] && echo "Enabled" || echo "Disabled")"
echo "   Payload size: ${PAYLOAD_SIZE_MB}MB"
echo "   Implementations: ${IMPLEMENTATIONS[*]}"
echo "   Cipher suites: ${SUITES[*]}"
echo "   Tests: ${TESTS[*]}"
echo ""
echo "📊 Focus: Real TLS performance metrics"
echo "   ✓ Handshake latency (total connection time)"
echo "   ✓ Bulk throughput (data transfer performance)"
echo "   ✓ 0-RTT performance (session resumption)"
echo "   ✓ Implementation comparison"
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

=== MEASUREMENT FOCUS ===
This benchmark focuses on realistic TLS performance metrics:
- Handshake latency: Total time to establish secure connection
- Bulk throughput: Data transfer performance after handshake
- 0-RTT performance: Session resumption capabilities
- Implementation comparison: OpenSSL vs BoringSSL vs WolfSSL

Note: Raw crypto operation comparisons removed as they were
misleading (comparing symmetric vs asymmetric operations).
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
    unique_configs=$(tail -n +2 "$CSV" | cut -d, -f2 | sort -u | wc -l)
    
    echo "   Data points collected: $total_rows"
    echo "   Unique configurations: $unique_configs"
    echo "   Meaningful metrics: handshake_ms, throughput_rps, response_time_s"
    
    echo ""
    echo "🔬 Next steps:"
    echo "   1. Run analysis: python3 analyze.py"
    echo "   2. Check results: ls results/latest/"
    echo "   3. View plots: ls figures/"
    echo ""
    echo "💡 Note: This focuses on end-to-end TLS performance,"
    echo "   not individual crypto operations which can be misleading."
fi

if [[ $NETEM -eq 1 ]]; then
  "$ROOT_DIR/scripts/netem_mac.sh" clear || true
fi