#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Parameters (override via env)
PAYLOADS=(${PAYLOADS:-0.1 1 10})
CONCURRENCIES=(${CONCURRENCIES:-1 8 32})
PROFILES=(${PROFILES:-P0 P1 P2 P3})
DO_0RTT=${DO_0RTT:-1}           # 1 to run 0-RTT
ORTT_PAYLOADS=(${ORTT_PAYLOADS:-0.1 1})
REQUESTS=${REQUESTS:-64}
SAMPLES=${SAMPLES:-33}          # analyze.py will drop first WARMUP_DROP (default 3)
COUNT_0RTT=${COUNT_0RTT:-10}
PORTS=(${PORTS:-4431 4432 8443 4434 4435 11112})

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
RUN_ROOT="$ROOT_DIR/results/run_matrix_${TIMESTAMP}"
mkdir -p "$RUN_ROOT"

copy_result() {
  # $1: src path, $2: dst dir, $3: aes tag (on/off)
  local src="$1" dst_dir="$2" aes="$3"
  [[ -f "$src" ]] || return 0
  mkdir -p "$dst_dir"
  local base
  base=$(basename "$src")
  local name="${base%.json}_${aes}.json"
  cp "$src" "$dst_dir/$name"
}

apply_aes() {
  local mode=$1
  if [[ "$mode" == "off" ]]; then
    export OPENSSL_ia32cap="~0x200000200000000"
  else
    unset OPENSSL_ia32cap
  fi
}

# Orchestration
for aes in on off; do
  apply_aes "$aes"
  AES_DIR="$RUN_ROOT/aes_${aes}"
  mkdir -p "$AES_DIR"

  for profile in "${PROFILES[@]}"; do
    echo "==> Applying NetEm profile: $profile"
    "$ROOT_DIR/scripts/netem_profiles.sh" "$profile"
    PROFILE_DIR="$AES_DIR/$profile"
    mkdir -p "$PROFILE_DIR"

    echo "==> Handshake (${SAMPLES} samples)"
    SAMPLES="$SAMPLES" "$ROOT_DIR/scripts/run_handshake.sh" >/dev/null || true
    # Copy from new organized folder structure
    for p in "${PORTS[@]}"; do
      # Try to find results in new organized folders first
      src_file=""
      aes_tag="aes_${aes}"
      if [[ -f "$ROOT_DIR/results/handshake/baseline_${aes_tag}_s${SAMPLES}/handshake_${p}_s${SAMPLES}.json" ]]; then
        src_file="$ROOT_DIR/results/handshake/baseline_${aes_tag}_s${SAMPLES}/handshake_${p}_s${SAMPLES}.json"
      elif [[ -f "$ROOT_DIR/results/handshake/delay_50ms_${aes_tag}_s${SAMPLES}/handshake_${p}_s${SAMPLES}.json" ]]; then
        src_file="$ROOT_DIR/results/handshake/delay_50ms_${aes_tag}_s${SAMPLES}/handshake_${p}_s${SAMPLES}.json"
      elif [[ -f "$ROOT_DIR/results/handshake/delay_50ms_loss_0.5_${aes_tag}_s${SAMPLES}/handshake_${p}_s${SAMPLES}.json" ]]; then
        src_file="$ROOT_DIR/results/handshake/delay_50ms_loss_0.5_${aes_tag}_s${SAMPLES}/handshake_${p}_s${SAMPLES}.json"
      elif [[ -f "$ROOT_DIR/results/handshake/delay_100ms_${aes_tag}_s${SAMPLES}/handshake_${p}_s${SAMPLES}.json" ]]; then
        src_file="$ROOT_DIR/results/handshake/delay_100ms_${aes_tag}_s${SAMPLES}/handshake_${p}_s${SAMPLES}.json"
      fi
      if [[ -n "$src_file" ]]; then
        copy_result "$src_file" "$PROFILE_DIR/handshake" "$aes"
      fi
    done

    echo "==> Bulk throughput matrix"
    for payload in "${PAYLOADS[@]}"; do
      for conc in "${CONCURRENCIES[@]}"; do
        REQUESTS="$REQUESTS" PAYLOAD_SIZE_MB="$payload" CONCURRENCY="$conc" \
          "$ROOT_DIR/scripts/run_bulk.sh" >/dev/null || true
        for p in "${PORTS[@]}"; do
          # Try to find results in new organized folders first
          src_file=""
          aes_tag="aes_${aes}"
          if [[ -f "$ROOT_DIR/results/bulk/baseline_${aes_tag}_r${REQUESTS}_p${payload}_c${conc}/bulk_${p}_r${REQUESTS}_p${payload}_c${conc}.json" ]]; then
            src_file="$ROOT_DIR/results/bulk/baseline_${aes_tag}_r${REQUESTS}_p${payload}_c${conc}/bulk_${p}_r${REQUESTS}_p${payload}_c${conc}.json"
          elif [[ -f "$ROOT_DIR/results/bulk/delay_50ms_${aes_tag}_r${REQUESTS}_p${payload}_c${conc}/bulk_${p}_r${REQUESTS}_p${payload}_c${conc}.json" ]]; then
            src_file="$ROOT_DIR/results/bulk/delay_50ms_${aes_tag}_r${REQUESTS}_p${payload}_c${conc}/bulk_${p}_r${REQUESTS}_p${payload}_c${conc}.json"
          elif [[ -f "$ROOT_DIR/results/bulk/delay_50ms_loss_0.5_${aes_tag}_r${REQUESTS}_p${payload}_c${conc}/bulk_${p}_r${REQUESTS}_p${payload}_c${conc}.json" ]]; then
            src_file="$ROOT_DIR/results/bulk/delay_50ms_loss_0.5_${aes_tag}_r${REQUESTS}_p${payload}_c${conc}/bulk_${p}_r${REQUESTS}_p${payload}_c${conc}.json"
          elif [[ -f "$ROOT_DIR/results/bulk/delay_100ms_${aes_tag}_r${REQUESTS}_p${payload}_c${conc}/bulk_${p}_r${REQUESTS}_p${payload}_c${conc}.json" ]]; then
            src_file="$ROOT_DIR/results/bulk/delay_100ms_${aes_tag}_r${REQUESTS}_p${payload}_c${conc}/bulk_${p}_r${REQUESTS}_p${payload}_c${conc}.json"
          fi
          if [[ -n "$src_file" ]]; then
            copy_result "$src_file" "$PROFILE_DIR/bulk/p${payload}_c${conc}" "$aes"
          fi
        done
      done
    done

    if [[ "$DO_0RTT" -eq 1 ]]; then
      echo "==> 0-RTT"
      for op in "${ORTT_PAYLOADS[@]}"; do
        EARLY_DATA_MB="$op" COUNT="$COUNT_0RTT" "$ROOT_DIR/scripts/run_0rtt.sh" >/dev/null || true
        for p in 4431 4432 8443; do
          # Try to find results in new organized folders first
          src_file=""
          aes_tag="aes_${aes}"
          if [[ -f "$ROOT_DIR/results/0rtt/baseline_${aes_tag}_ed${op}_n${COUNT_0RTT}/simple_${p}_ed${op}_n${COUNT_0RTT}.json" ]]; then
            src_file="$ROOT_DIR/results/0rtt/baseline_${aes_tag}_ed${op}_n${COUNT_0RTT}/simple_${p}_ed${op}_n${COUNT_0RTT}.json"
          elif [[ -f "$ROOT_DIR/results/0rtt/delay_50ms_${aes_tag}_ed${op}_n${COUNT_0RTT}/simple_${p}_ed${op}_n${COUNT_0RTT}.json" ]]; then
            src_file="$ROOT_DIR/results/0rtt/delay_50ms_${aes_tag}_ed${op}_n${COUNT_0RTT}/simple_${p}_ed${op}_n${COUNT_0RTT}.json"
          elif [[ -f "$ROOT_DIR/results/0rtt/delay_50ms_loss_0.5_${aes_tag}_ed${op}_n${COUNT_0RTT}/simple_${p}_ed${op}_n${COUNT_0RTT}.json" ]]; then
            src_file="$ROOT_DIR/results/0rtt/delay_50ms_loss_0.5_${aes_tag}_ed${op}_n${COUNT_0RTT}/simple_${p}_ed${op}_n${COUNT_0RTT}.json"
          elif [[ -f "$ROOT_DIR/results/0rtt/delay_100ms_${aes_tag}_ed${op}_n${COUNT_0RTT}/simple_${p}_ed${op}_n${COUNT_0RTT}.json" ]]; then
            src_file="$ROOT_DIR/results/0rtt/delay_100ms_${aes_tag}_ed${op}_n${COUNT_0RTT}/simple_${p}_ed${op}_n${COUNT_0RTT}.json"
          fi
          if [[ -n "$src_file" ]]; then
            copy_result "$src_file" "$PROFILE_DIR/0rtt/ed${op}" "$aes"
          fi
        done
      done
    fi

    echo "-- Snapshot done for $profile / AES $aes"
  done

done

# Clear NetEm at the end
"$ROOT_DIR/scripts/netem_profiles.sh" clear || true

echo "✓ Matrix run saved under: $RUN_ROOT" 