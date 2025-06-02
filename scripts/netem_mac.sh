#!/usr/bin/env bash
set -euo pipefail

PF_CONF=/etc/pf.conf
PF_BACKUP=/etc/pf.conf.backup
TAG="# TLS_THESIS_NETEM"
PIPE=1

usage() { 
    echo "Usage: $0 <delay_ms> <loss_frac_0-1> | clear"
    echo "Examples:"
    echo "  $0 50 0.01     # 50ms delay, 1% packet loss"
    echo "  $0 100 0.05    # 100ms delay, 5% packet loss"
    echo "  $0 clear       # remove all rules"
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
        
    if ! [[ "$delay_ms" =~ ^[0-9]+$ ]] || (( delay_ms < 0 || delay_ms > 1000 )); then
        echo "❌ Delay musi być liczbą 0-1000 ms"
        exit 1
    fi
    
    if ! [[ "$loss_frac" =~ ^0*\.?[0-9]+$ ]]; then
        echo "❌ Loss musi być liczbą zmiennoprzecinkową 0-1"
        exit 1
    fi
        
    loss_pct=$(echo "scale=1; $loss_frac * 100" | bc)
    
    echo "🌐 Konfiguruję NetEm: delay=${delay_ms}ms, loss=${loss_pct}%"
        
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
    
    echo "✅ NetEm aktywny: delay=${delay_ms}ms, loss=${loss_pct}%"
    
    echo "📊 Status:"
    sudo dnctl list | grep "pipe $PIPE" || echo "  (brak aktywnych pipe)"
}

if [[ "$(uname)" != "Darwin" ]]; then
    echo "❌ Ten skrypt działa tylko na macOS"
    echo "   Dla Linux użyj: tc qdisc add dev eth0 root netem delay ${1}ms loss ${2}%"
    exit 1
fi

if [[ $# -eq 0 ]]; then
    usage
elif [[ $# -eq 1 && "$1" == "clear" ]]; then
    clear_netem
elif [[ $# -eq 2 ]]; then
    apply_netem "$1" "$2"
else
    usage
fi