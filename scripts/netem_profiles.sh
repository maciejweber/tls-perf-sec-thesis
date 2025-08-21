#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

profile=${1:-}
if [[ -z "$profile" ]]; then
  echo "Usage: $0 <P0|P1|P2|P3|clear>" >&2
  echo "P0: 0ms, 0%" >&2
  echo "P1: 50ms, jitter nominal (macOS ignores jitter)" >&2
  echo "P2: 50ms, 0.5% loss" >&2
  echo "P3: 100ms, 0%" >&2
  exit 1
fi

case "$profile" in
  P0|p0)
    "$ROOT_DIR/scripts/netem_mac.sh" 0 0 ;;
  P1|p1)
    # macOS dummynet ignores jitter; approximate with 50ms, 0% loss
    "$ROOT_DIR/scripts/netem_mac.sh" 50 0 ;;
  P2|p2)
    "$ROOT_DIR/scripts/netem_mac.sh" 50 0.005 ;;
  P3|p3)
    "$ROOT_DIR/scripts/netem_mac.sh" 100 0 ;;
  clear)
    "$ROOT_DIR/scripts/netem_mac.sh" clear ;;
  *)
    echo "Unknown profile: $profile" >&2; exit 1 ;;
fi

echo "OK: applied $profile" 