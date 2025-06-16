# #!/usr/bin/env bash
# set -e

# caffeinate -dims &
# KEEP=$!

# ITERATIONS=1 NETEM=0 MEASURE_RESOURCES=0 ./scripts/run_all.sh

# DISABLE_AESNI=1 ITERATIONS=1 NETEM=0 MEASURE_RESOURCES=0 ./scripts/run_all.sh

# kill "$KEEP"

#!/usr/bin/env bash
set -euo pipefail

caffeinate -dims &
KEEP=$!

echo "🔐 AES-NI ON"
PAYLOAD_SIZE_MB=1024 \
ITERATIONS=30 \
NETEM=1 \
NETEM_DELAY=50 \
NETEM_LOSS=0.01 \
MEASURE_RESOURCES=1 \
./scripts/run_all.sh

echo "🚫 AES-NI OFF"
DISABLE_AESNI=1 \
PAYLOAD_SIZE_MB=1024 \
ITERATIONS=30 \
NETEM=1 \
NETEM_DELAY=50 \
NETEM_LOSS=0.01 \
MEASURE_RESOURCES=1 \
./scripts/run_all.sh

kill "$KEEP"
