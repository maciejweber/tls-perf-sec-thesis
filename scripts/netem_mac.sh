#!/usr/bin/env bash
set -euo pipefail

PF_CONF=/etc/pf.conf
PF_BACKUP=/etc/pf.conf.backup
TAG="# TLS_THESIS_NETEM"
PIPE=1

usage() { 
    echo "Usage: $0 <delay_ms> <loss_frac_0-1> [jitter_ms] | clear"
    echo "Examples:"
    echo "  $0 50 0.01           # 50ms delay, 1% packet loss"
    echo "  $0 100 0.005 10      # +jitter=10ms (note: macOS dummynet ignores jitter)"
    echo "  $0 clear             # remove all rules"
    exit 1
}

clear_netem() {
    echo "🧹 Czyszczę reguły NetEm..."
        
    sudo dnctl -q delete pipe $PIPE 2>/dev/null || true
        
    if [[ -f "$PF_BACKUP" ]]; then
        sudo cp "$PF_BACKUP" "$PF_CONF"
        sudo rm "$PF_BACKUP"
    else        
        sudo sed -i '' "/${TAG}$/d" "$PF_CONF" 2>/dev/null || true
    fi
        
    sudo pfctl -d 2>/dev/null || true
    
    echo "✅ NetEm wyczyszczony"
}

apply_netem() {
    local delay_ms="$1"
    local loss_frac="$2"
    local jitter_ms="${3:-0}"
        
    if ! [[ "$delay_ms" =~ ^[0-9]+$ ]] || (( delay_ms < 0 || delay_ms > 1000 )); then
        echo "❌ Delay musi być liczbą 0-1000 ms"
        exit 1
    fi
    
    if ! [[ "$loss_frac" =~ ^0*\.?[0-9]+$ ]]; then
        echo "❌ Loss musi być liczbą zmiennoprzecinkową 0-1"
        exit 1
    fi
    
    if ! [[ "$jitter_ms" =~ ^[0-9]+$ ]]; then
        echo "❌ Jitter musi być liczbą całkowitą (ms)"
        exit 1
    fi
        
    loss_pct=$(echo "scale=1; $loss_frac * 100" | bc)
    
    echo "🌐 Konfiguruję NetEm: delay=${delay_ms}ms, loss=${loss_pct}%, jitter=${jitter_ms}ms"
    if [[ "$jitter_ms" != "0" ]]; then
        echo "ℹ️  Uwaga: macOS dummynet nie wspiera bezpośrednio jitteru jak Linux netem; parametr zostanie zignorowany."
    fi
        
    if [[ ! -f "$PF_BACKUP" ]]; then
        sudo cp "$PF_CONF" "$PF_BACKUP"
    fi
        
    sudo dnctl pipe $PIPE config delay "${delay_ms}ms" plr "$loss_frac"
        
    if ! grep -q "$TAG" "$PF_CONF"; then        
        cat <<EOF | sudo tee -a "$PF_CONF" >/dev/null

# TLS thesis network emulation $TAG
dummynet out proto tcp to any port {443, 4431, 4432, 8443} pipe $PIPE $TAG
EOF
    fi
    
    sudo pfctl -f "$PF_CONF" -e
    
    echo "✅ NetEm aktywny: delay=${delay_ms}ms, loss=${loss_pct}% (jitter=${jitter_ms}ms ignored on macOS)"
    
    echo "📊 Status:"
    sudo dnctl list | grep "pipe $PIPE" || echo "  (brak aktywnych pipe)"
}

if [[ "$(uname)" != "Darwin" ]]; then
    echo "❌ Ten skrypt działa tylko na macOS"
    echo "   Dla Linux użyj: tc qdisc add dev eth0 root netem delay ${1}ms ${3:-0}ms distribution normal loss $(echo "$2 * 100" | bc)%"
    exit 1
fi

if [[ $# -eq 0 ]]; then
    usage
elif [[ $# -eq 1 && "$1" == "clear" ]]; then
    clear_netem
elif [[ $# -ge 2 && $# -le 3 ]]; then
    apply_netem "$1" "$2" "${3:-0}"
else
    usage
fi