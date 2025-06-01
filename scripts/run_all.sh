#!/usr/bin/env bash
set -euo pipefail
sudo -v                                       # jedno pyt. o hasło na sesję

IMPLEMENTATIONS=(openssl boringssl wolfssl)
SUITES=(x25519_aesgcm chacha20)               # bez kyber_hybrid
TESTS=(handshake bulk 0rtt)
ITERATIONS=1                                  # zostaw 1 — ~2 min testu

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUTDIR="${ROOT_DIR}/results"
CSV="${OUTDIR}/bench_$(date +%F).csv"
mkdir -p "$OUTDIR"
[[ -f "$CSV" ]] || echo "implementation,suite,test,run,metric,value,unit" >"$CSV"

# mapa suite → port
port() { [[ $1 == x25519_aesgcm ]] && echo 4431 || echo 4432; }

# jednostki
unit() {
  case "$1" in mean_ms) echo ms;; mean_time_s) echo s;; rps) echo 1/s;; *) echo -;; esac
}

# konwersja JSON → wiersze CSV
pairs() {
  jq -Mr '
    to_entries
    | map(
        if .key|test("avg_(request_)?time")      then {k:"mean_time_s",v:.value}
        elif .key=="requests_per_second"        then {k:"rps",v:.value}
        elif .key|test("^(host|port|config|successful_|total_)") then empty
        else {k:.key,v:.value} end
      ) | .[] | "\(.k) \(.v)"
  ' "$1"
}

run_single() {
  local impl=$1 suite=$2 test=$3 run=$4
  local prt json
  prt=$(port "$suite")

  case "$test" in
    handshake) "${ROOT_DIR}/scripts/run_handshake.sh" >/dev/null ;;
    bulk)      "${ROOT_DIR}/scripts/run_bulk.sh"      >/dev/null ;;
    0rtt)      "${ROOT_DIR}/scripts/run_0rtt.sh"      >/dev/null ;;
  esac

  case "$test" in
    handshake) json="${OUTDIR}/handshake_${prt}.json" ;;
    bulk)      json="${OUTDIR}/bulk_${prt}.json"      ;;
    0rtt)      json="${OUTDIR}/simple_${prt}.json"    ;;
  esac
  [[ -f "$json" ]] || { echo "⚠️  brak ${json}"; return; }

  while read -r m v; do
    echo "${impl},${suite},${test},${run},${m},${v},$(unit "$m")" >>"$CSV"
  done < <(pairs "$json")
}

export -f run_single port unit pairs

for impl in "${IMPLEMENTATIONS[@]}"; do
  for suite in "${SUITES[@]}"; do
    for test in "${TESTS[@]}";  do
      run_single "$impl" "$suite" "$test" 1
    done
  done
done

echo "✔  Wyniki: $CSV"
