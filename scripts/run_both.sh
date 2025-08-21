#!/usr/bin/env bash
set -euo pipefail

caffeinate -dims &
KEEP=$!

echo "🔐 AES-NI ON"
PAYLOAD_SIZE_MB=1024 \
ITERATIONS=5 \
NETEM=1 \
NETEM_DELAY=50 \
NETEM_LOSS=0.01 \
MEASURE_RESOURCES=1 \
SUITES='x25519_aesgcm chacha20 kyber_hybrid' \
./scripts/run_all.sh

echo "🚫 AES-NI OFF"
DISABLE_AESNI=1 \
PAYLOAD_SIZE_MB=10 \
ITERATIONS=5 \
NETEM=1 \
NETEM_DELAY=50 \
NETEM_LOSS=0.01 \
MEASURE_RESOURCES=1 \
SUITES='x25519_aesgcm chacha20 kyber_hybrid' \
./scripts/run_all.sh

kill "$KEEP"