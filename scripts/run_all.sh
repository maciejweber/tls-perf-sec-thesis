#!/usr/bin/env bash
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
  case $1 in mean_ms) echo ms;;
             mean_time_s) echo s;;
             rps) echo 1/s;;
             *)  echo -;;
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

run_once() {
  local impl=$1 suite=$2 test=$3 run=$4
  echo "▶ $impl/$suite/$test #$run"
  local prt json ; prt=$(port "$suite")

  case $test in
    handshake) "$ROOT_DIR/scripts/run_handshake.sh" "$prt" >/dev/null ;;
    bulk)      
      "$ROOT_DIR/scripts/run_bulk.sh" "$prt" >/dev/null
      
      if [[ $MEASURE_RESOURCES -eq 1 && "$impl" == "openssl" ]]; then
        echo "  📊 Mierzę zasoby dla $suite..."
        
        case "$suite" in
          x25519_aesgcm) cmd="docker run --rm --network host openquantumsafe/oqs-ossl3 sh -c 'openssl speed -provider default -evp aes-128-gcm -seconds 1'" ;;
          chacha20)      cmd="docker run --rm --network host openquantumsafe/oqs-ossl3 sh -c 'openssl speed -provider default -evp chacha20-poly1305 -seconds 1'" ;;
          kyber_hybrid)  cmd="docker run --rm --network host openquantumsafe/oqs-ossl3 sh -c 'openssl speed -provider oqsprovider -provider default -seconds 1 X25519MLKEM768'" ;;
          *)             cmd="" ;;
        esac
        
        if [[ -n "$cmd" ]]; then
          if [[ $EUID -eq 0 ]] || sudo -n true 2>/dev/null; then
            sudo "$ROOT_DIR/scripts/measure_resources.sh" "$cmd" >/dev/null 2>&1 || true
          else
            "$ROOT_DIR/scripts/measure_resources.sh" "$cmd" >/dev/null 2>&1 || true
          fi
          
          latest_perf=$(ls -t "$ROOT_DIR/results"/combined_*.json 2>/dev/null | head -1)
          if [[ -f "$latest_perf" ]]; then
            cp "$latest_perf" "$RUN_DIR/perf_${impl}_${suite}_run${run}.json"
            
            mean_time=$(jq -r '.mean_time_ms' "$latest_perf")
            watts=$(jq -r '.package_watts' "$latest_perf")
            
            echo "$impl,$suite,perf,$run,resource_mean_ms,$mean_time,ms" >>"$CSV"
            echo "$impl,$suite,perf,$run,package_watts,$watts,W" >>"$CSV"
          fi
        fi
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

for impl in "${IMPLEMENTATIONS[@]}"; do
  for suite in "${SUITES[@]}";     do
    for test  in "${TESTS[@]}";    do
      for run  in $(seq "$ITERATIONS"); do
        run_once "$impl" "$suite" "$test" "$run"
      done
    done
  done
done

END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))
DURATION_MIN=$((DURATION / 60))
DURATION_SEC=$((DURATION % 60))

echo "" >> "$RUN_DIR/config.txt"
echo "Duration: ${DURATION_MIN}m ${DURATION_SEC}s" >> "$RUN_DIR/config.txt"

if [[ -d "$ROOT_DIR/results/raw" ]]; then
  cp -r "$ROOT_DIR/results/raw" "$RUN_DIR/"
fi

find "$ROOT_DIR/results" -name "hf_*.json" -o -name "pm_*.txt" -o -name "combined_*.json" | \
  grep -v "$RUN_DIR" | xargs rm -f 2>/dev/null || true

ln -sfn "$RUN_DIR" "$ROOT_DIR/results/latest"

echo "✔  Wyniki zapisane w: $RUN_DIR"
echo "✔  Czas trwania: ${DURATION_MIN}m ${DURATION_SEC}s"
echo "✔  Link do najnowszego: results/latest"

if [[ $NETEM -eq 1 ]]; then
  "$ROOT_DIR/scripts/netem_mac.sh" clear || true
fi