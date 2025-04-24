#!/usr/bin/env bash
# ------------------------------------------------------------
# run_0rtt.sh — zysk z 0-RTT (time_starttransfer)
# ------------------------------------------------------------
# Co mierzymy i dlaczego:
#   • curl --http2-prior-knowledge  — pomija ALPN
#   • porównujemy z i bez  --tls13-early-data
# ------------------------------------------------------------
need=(curl jq openssl)

for bin in openssl jq wrk2; do
  command -v $bin >/dev/null || { echo "❌ $bin not found"; exit 1; }
done

set -euo pipefail
HOST="${1-localhost}"
PORT="${2-4431}"

curl_base=(curl -k --http2-prior-knowledge -o /dev/null -s -w '%{time_starttransfer}\n')
base=$("${curl_base[@]}" "https://${HOST}:${PORT}/")

# wymuszamy resumption: jedno żądanie „rozgrzewające”
curl -k --http2-prior-knowledge -o /dev/null -s "https://${HOST}:${PORT}/"

early=$("${curl_base[@]/curl/curl --tls13-early-data @/dev/null}" \
        "https://${HOST}:${PORT}/")

jq -n --arg base "$base" --arg early "$early" '
  {t_full_ms:($base|tonumber*1000)|round,
   t_0rtt_ms:($early|tonumber*1000)|round,
   gain_ms:(($base|tonumber-$early|tonumber)*1000)|round}' \
  | tee "results/0rtt_${PORT}.json"
