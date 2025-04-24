#!/usr/bin/env bash
# ------------------------------------------------------------
# run_handshake.sh — pomiar średniego czasu pełnego handshake TLS 1.3
# ------------------------------------------------------------
# Co mierzymy i dlaczego:
#   • openssl s_time -new  — wymusza handshake bez resumption
#   • 5 × 15 s  → redukuje jednorazowe skoki CPU/sieć
# Wynik JSON: {"mean_ms": X, "std_ms": Y}
# ------------------------------------------------------------
need=(openssl jq)    

for bin in openssl jq wrk2; do
  command -v $bin >/dev/null || { echo "❌ $bin not found"; exit 1; }
done

set -euo pipefail
HOST="${1-localhost}"
PORT="${2-4431}"
REPS=5
DUR=15

vals=()
for ((i=1;i<=REPS;i++)); do
  line=$(openssl s_time -new -connect "${HOST}:${PORT}" -time "$DUR" 2>&1 \
         | awk '/connections in/ {print $0}')
  conns=$(awk '{print $1}' <<<"$line")
  secs=$(awk '{print $(NF-1)}' <<<"$line" | tr -d 's;')
  ms=$(awk "BEGIN{printf \"%.4f\", ($secs/$conns)*1000}")
  vals+=("$ms")
done

sum=0; for v in "${vals[@]}"; do sum=$(awk "BEGIN{print $sum+$v}"); done
mean=$(awk "BEGIN{print $sum/${#vals[@]} }")
ss=0; for v in "${vals[@]}"; do ss=$(awk "BEGIN{print $ss+($v-$mean)^2}"); done
std=$(awk "BEGIN{print sqrt($ss/(${#vals[@]}-1))}")

printf '{"mean_ms": %.4f, "std_ms": %.4f}\n' "$mean" "$std" \
  | tee "results/handshake_${PORT}.json"
