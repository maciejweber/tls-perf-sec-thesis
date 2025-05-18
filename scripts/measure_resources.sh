#!/usr/bin/env bash

# usage:
# sudo ./scripts/measure_resources.sh "openssl speed -evp aes-128-gcm"
# sudo ./scripts/measure_resources.sh "openssl speed -evp chacha20-poly1305"
# sudo ./scripts/measure_resources.sh "openssl speed -evp aes-256-gcm"

set -euo pipefail

CMD="$1"
RUNS=5
OUTDIR="results"
mkdir -p "$OUTDIR"

for bin in hyperfine jq powermetrics; do
  command -v "$bin" >/dev/null || { echo "$bin not found"; exit 1; }
done

sudo -v                                       # jedno pytanie o hasło

TS=$(date +%s)
HF_JSON="$OUTDIR/hf_${TS}.json"
PM_TXT="$OUTDIR/pm_${TS}.txt"
OUT_JSON="$OUTDIR/combined_${TS}.json"

# --- 1. hyperfine ------------------------------------------------------------
hyperfine --runs "$RUNS" --export-json "$HF_JSON" "$CMD"

# --- 2. powermetrics (jedna 2-sekundowa próbka) ------------------------------
sudo powermetrics -n 1 -i 2000 --samplers cpu_power >"$PM_TXT" 2>/dev/null || true

# --- 3. metryki --------------------------------------------------------------
MEAN_MS=$(jq '.results[0].mean * 1000'    "$HF_JSON")
STD_MS=$( jq '.results[0].stddev * 1000'  "$HF_JSON")
CPU_CYCLES=$(jq '.results[0].user_cycles // 0' "$HF_JSON") 
PKG_WATTS=$(awk '/Average accumulated package power:/ {sum+=$5;n++}
                 END{if(n)printf "%.2f",sum/n}' "$PM_TXT")
[[ -z "$PKG_WATTS" ]] && PKG_WATTS=0  

jq -n \
  --arg cmd  "$CMD" \
  --arg mean "$MEAN_MS" \
  --arg std  "$STD_MS" \
  --arg cyc  "$CPU_CYCLES" \
  --arg wat  "${PKG_WATTS:-0}" \
  '{
     command:        $cmd,
     mean_time_ms:   ($mean|tonumber),
     std_ms:         ($std|tonumber),
     cpu_cycles:     ($cyc|tonumber),
     package_watts:  ($wat|tonumber)
   }' >"$OUT_JSON"

echo "✅ metrics saved to $OUT_JSON"
