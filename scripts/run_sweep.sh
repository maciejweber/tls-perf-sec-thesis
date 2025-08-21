#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Defaults
PAYLOADS=(${PAYLOADS:-0.1 1 10})
CONCURRENCIES=(${CONCURRENCIES:-1 8 32})
IMPLEMENTATIONS=(${IMPLEMENTATIONS:-openssl wolfssl})
SUITES=(${SUITES:-x25519_aesgcm chacha20 kyber_hybrid})
ITERATIONS=${ITERATIONS:-1}
REQUESTS=${REQUESTS:-64}

export IMPLEMENTATIONS SUITES ITERATIONS REQUESTS

echo "==== Sweep payload × concurrency ===="
for p in "${PAYLOADS[@]}"; do
  for c in "${CONCURRENCIES[@]}"; do
    echo "-- payload=${p}MB, concurrency=${c} --"
    PAYLOAD_SIZE_MB="$p" CONCURRENCY="$c" TESTS=bulk "$ROOT_DIR/scripts/run_all.sh"
  done
done

echo "✅ Sweep complete" 