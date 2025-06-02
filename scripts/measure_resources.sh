#!/usr/bin/env bash

# usage:
# ./scripts/measure_resources.sh "openssl speed -evp aes-128-gcm -seconds 1"

set -euo pipefail

CMD="$1"
RUNS=3
OUTDIR="results"
mkdir -p "$OUTDIR"

command -v hyperfine >/dev/null || { echo "❌ hyperfine not found"; exit 1; }

TS=$(date +%s)
HF_JSON="$OUTDIR/hf_${TS}.json"
OUT_JSON="$OUTDIR/combined_${TS}.json"

echo "📊 Uruchamiam hyperfine..."
if hyperfine --runs "$RUNS" --warmup 1 --export-json "$HF_JSON" "$CMD"; then
    echo "✅ Hyperfine zakończony"
else
    echo "❌ Hyperfine failed"
    exit 1
fi

PKG_WATTS=0
if [[ "$(uname)" == "Darwin" ]] && command -v powermetrics >/dev/null 2>&1; then
    echo "📊 Próba pomiaru mocy..."
        
    PM_TXT="$OUTDIR/pm_${TS}.txt"
        
    {
        sleep 0.5
        sudo powermetrics -n 1 -i 2000 --samplers cpu_power 2>/dev/null | \
            grep -i "package power" | \
            grep -oE '[0-9]+\.[0-9]+' | \
            head -1 > "$PM_TXT" || echo "0" > "$PM_TXT"
    } &
    
    bash -c "$CMD" >/dev/null 2>&1
        
    wait
        
    PKG_WATTS=$(cat "$PM_TXT" 2>/dev/null || echo "0")
    rm -f "$PM_TXT"
    
    echo "📊 Zmierzona moc: ${PKG_WATTS}W"
fi

if [[ -f "$HF_JSON" ]]; then
    MEAN_MS=$(jq -r '.results[0].mean * 1000' "$HF_JSON" 2>/dev/null || echo "0")
    STD_MS=$(jq -r '.results[0].stddev * 1000' "$HF_JSON" 2>/dev/null || echo "0")
    
    echo "📊 Średni czas: ${MEAN_MS}ms (±${STD_MS}ms)"
else
    echo "❌ Brak pliku $HF_JSON"
    exit 1
fi

jq -n \
  --arg cmd  "$CMD" \
  --arg mean "$MEAN_MS" \
  --arg std  "$STD_MS" \
  --arg wat  "${PKG_WATTS:-0}" \
  '{
     command:           $cmd,
     mean_time_ms:      ($mean|tonumber),
     std_ms:            ($std|tonumber),
     package_watts:     ($wat|tonumber)
   }' >"$OUT_JSON"

echo "✅ Metryki zapisane w: $OUT_JSON"

cat "$OUT_JSON"

rm -f "$HF_JSON" 2>/dev/null || true