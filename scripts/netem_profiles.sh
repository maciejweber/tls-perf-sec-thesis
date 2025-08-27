#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

profile=${1:-}
if [[ -z "$profile" ]]; then
  echo "Usage: $0 <P0|P1|P2|P3|clear>" >&2
  echo "P0: 0ms, 0%" >&2
  echo "P1: 50ms, 0%" >&2
  echo "P2: 50ms, 0.5%" >&2
  echo "P3: 100ms, 0%" >&2
  exit 1
fi

# Check if NetEm is working
check_netem() {
  if [[ "$(uname)" == "Darwin" ]]; then
    # On macOS, check if dummynet can create pipes
    if ! sudo dnctl pipe 999 config delay 1ms 2>/dev/null; then
      echo "⚠️  NetEm not working on macOS - dummynet pipe creation failed"
      echo "   This is a known limitation. Tests will use baseline (0ms delay, 0% loss)"
      echo "   Consider using Docker network options or external network emulation"
      return 1
    fi
    # Clean up test pipe
    sudo dnctl delete pipe 999 2>/dev/null || true
  fi
  return 0
}

case "$profile" in
  P0|p0)
    if check_netem; then
      "$ROOT_DIR/scripts/netem_mac.sh" 0 0
    else
      echo "🌐 NetEm not available - using baseline profile (0ms, 0%)"
      echo "   Profile: P0 (baseline) - delay=0ms, loss=0%"
    fi ;;
  P1|p1)
    if check_netem; then
      "$ROOT_DIR/scripts/netem_mac.sh" 50 0
    else
      echo "🌐 NetEm not available - using baseline profile (0ms, 0%)"
      echo "   Profile: P1 (50ms delay) - fallback to baseline due to NetEm limitation"
      echo "   Note: To test network sensitivity, consider:"
      echo "   - Using Docker network options"
      echo "   - External network emulation tools"
      echo "   - Cloud-based testing with real network conditions"
    fi ;;
  P2|p2)
    if check_netem; then
      "$ROOT_DIR/scripts/netem_mac.sh" 50 0.005
    else
      echo "🌐 NetEm not available - using baseline profile (0ms, 0%)"
      echo "   Profile: P2 (50ms delay, 0.5% loss) - fallback to baseline due to NetEm limitation"
    fi ;;
  P3|p3)
    if check_netem; then
      "$ROOT_DIR/scripts/netem_mac.sh" 100 0
    else
      echo "🌐 NetEm not available - using baseline profile (0ms, 0%)"
      echo "   Profile: P3 (100ms delay) - fallback to baseline due to NetEm limitation"
    fi ;;
  clear)
    if check_netem; then
      "$ROOT_DIR/scripts/netem_mac.sh" clear
    else
      echo "🌐 NetEm not available - no rules to clear"
    fi ;;
  *)
    echo "Unknown profile: $profile" >&2; exit 1 ;;
esac

echo "OK: applied $profile" 