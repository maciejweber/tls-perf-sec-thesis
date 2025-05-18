#!/usr/bin/env bash
set -euo pipefail

sudo -v

IMPLEMENTATIONS=(openssl boringssl wolfssl)
SUITES=(x25519_aesgcm chacha20 kyber_hybrid)
TESTS=(handshake bulk 0rtt)
ITERATIONS=30

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CSV="${ROOT_DIR}/results/bench_$(date +%F).csv"
mkdir -p "$(dirname "$CSV")"
[[ -f "$CSV" ]] || echo "implementation,suite,test,run,metric,value,unit" >"$CSV"

measure_cmd() {
  case "$1" in
    x25519_aesgcm) echo "openssl speed -evp aes-128-gcm" ;;
    chacha20) echo "openssl speed -evp chacha20-poly1305" ;;
    kyber_hybrid) echo "openssl speed -evp aes-256-gcm" ;;
    *) echo "openssl speed aes" ;;
  esac
}

guess_unit() {
  case "$1" in
    *ms) echo "ms" ;;
    *_s|*time|*seconds) echo "s" ;;
    *watt*|*Watts*) echo "W" ;;
    *cycles) echo "cycles" ;;
    *bytes*|*_B) echo "bytes" ;;
    *) echo "-" ;;
  esac
}

progress() { printf "\r%-60s" "$*"; }

run_single() {
  local impl="$1" suite="$2" test="$3" run="$4"
  progress "[${impl}/${suite}/${test}] ${run}/${ITERATIONS}"
  env IMPLEMENTATION="$impl" SUITE="$suite" "${ROOT_DIR}/scripts/run_${test}.sh" >/dev/null 2>&1 || true
  local tmp
  tmp="$("${ROOT_DIR}/scripts/measure_resources.sh" "$(measure_cmd "$suite")" | awk '/metrics saved to/ {print $NF}')"
  [[ -f "$tmp" ]] || { echo -e "\nmissing metrics for $impl/$suite/$test"; return; }
  jq -r 'to_entries[] | "\(.key) \(.value)"' "$tmp" | while read -r metric value; do
    echo "${impl},${suite},${test},${run},${metric},${value},$(guess_unit "$metric")" >>"$CSV"
  done
}

export -f run_single measure_cmd guess_unit progress

if [[ ${1:-} == "--parallel" ]]; then
  mapfile -t TASKS < <(
    for i in "${IMPLEMENTATIONS[@]}"; do
      for s in "${SUITES[@]}"; do
        for t in "${TESTS[@]}"; do
          for r in $(seq 1 "$ITERATIONS"); do
            echo "$i $s $t $r"
          done
        done
      done
    done
  )
  printf '%s\n' "${TASKS[@]}" | parallel --jobs 4 --colsep ' ' run_single {1} {2} {3} {4}
else
  for impl in "${IMPLEMENTATIONS[@]}"; do
    for suite in "${SUITES[@]}"; do
      for test in "${TESTS[@]}"; do
        for run in $(seq 1 "$ITERATIONS"); do
          run_single "$impl" "$suite" "$test" "$run"
        done
      done
    done
  done
fi

echo -e "\nCompleted: results saved to $CSV"
