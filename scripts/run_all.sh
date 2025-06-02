#!/usr/bin/env bash
set -euo pipefail
sudo -v                       

IMPLEMENTATIONS=(openssl boringssl wolfssl)
SUITES=(x25519_aesgcm chacha20 kyber_hybrid)
TESTS=(handshake bulk 0rtt)
ITERATIONS=${ITERATIONS:-30}  

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"


TIMESTAMP=$(date +%Y%m%d_%H%M%S)
RUN_DIR="$ROOT_DIR/results/run_${TIMESTAMP}"
mkdir -p "$RUN_DIR"


cat > "$RUN_DIR/config.txt" <<EOF
Timestamp: $TIMESTAMP
Date: $(date)
Iterations: $ITERATIONS
Implementations: ${IMPLEMENTATIONS[@]}
Suites: ${SUITES[@]}
Tests: ${TESTS[@]}
REQUESTS: ${REQUESTS:-100}
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
    bulk)      "$ROOT_DIR/scripts/run_bulk.sh"      "$prt" >/dev/null ;;
    0rtt)      "$ROOT_DIR/scripts/run_0rtt.sh"      "$prt" >/dev/null ;;
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


ln -sfn "$RUN_DIR" "$ROOT_DIR/results/latest"

echo "✔  Wyniki zapisane w: $RUN_DIR"
echo "✔  Czas trwania: ${DURATION_MIN}m ${DURATION_SEC}s"
echo "✔  Link do najnowszego: results/latest"