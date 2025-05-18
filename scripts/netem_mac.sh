#!/usr/bin/env bash
set -euo pipefail

PF_CONF=/etc/pf.conf
TAG="# TLS_THESIS_NETEM"
PIPE=1

usage(){ echo "usage: $0 <delay_ms> <loss_frac_0-1> | clear" >&2; exit 1; }

clear_netem(){
  sudo dnctl -q delete pipe $PIPE 2>/dev/null || true
  sudo sed -i '' "/${TAG}$/d" "$PF_CONF"
  sudo pfctl -d
  echo "cleared"
}

apply_netem(){
  local d="$1" l="$2"
  sudo dnctl pipe $PIPE config delay "${d}ms" plr "$l"
  grep -q "$TAG" "$PF_CONF" || \
    echo "dummynet out proto tcp to any port 443 pipe $PIPE $TAG" \
    | sudo tee -a "$PF_CONF" >/dev/null
  sudo pfctl -f "$PF_CONF" -e
  echo "delay=${d}ms loss=${l}"
}

[[ $# -eq 1 && $1 == clear ]] && { clear_netem; exit; }
[[ $# -eq 2 ]] || usage
apply_netem "$1" "$2"
