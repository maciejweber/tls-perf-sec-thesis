#!/usr/bin/env bash
set -euo pipefail
# macOS: proste "bytes-on-the-wire" dla TLS 1.3 na porcie/portach (domyślnie 4431 4432 4434 4435)
# Wymagania: brew install wireshark  (daje tshark); curl (w systemie)
# Użycie:
#   ./scripts/bytes_on_wire_mac.sh
#   ./scripts/bytes_on_wire_mac.sh 4431 4432        # własne porty
#   DRIVE=0 DURATION=10 ./scripts/bytes_on_wire_mac.sh 8443 11112   # pasywny capture dla PQ — wyzwól handshake klientem PQ w oknie czasu
# Wynik: results/bytes_on_the-wire/<profile>/bytes_on_wire_mac.csv

DURATION=${DURATION:-6}          # czas przechwytywania na port (sekundy)
HITS=${HITS:-6}                  # ile żądań curl na port (żeby handshake na pewno był)
DRIVE=${DRIVE:-1}                # 1=generuj ruch curl; 0=nie generuj (pasywnie)
OUTDIR=${OUTDIR:-results}

# Determine NetEm profile from current network conditions
get_netem_profile() {
  # Check if NetEm is active and determine profile
  if command -v dnctl >/dev/null 2>&1; then
    local pipe_info=$(dnctl list 2>/dev/null | grep "pipe 1" || echo "")
    if [[ -n "$pipe_info" ]]; then
      if echo "$pipe_info" | grep -q "delay 50ms.*plr 0.005"; then
        echo "delay_50ms_loss_0.5"  # P2
      elif echo "$pipe_info" | grep -q "delay 50ms.*plr 0"; then
        echo "delay_50ms"           # P1
      elif echo "$pipe_info" | grep -q "delay 100ms.*plr 0"; then
        echo "delay_100ms"          # P3
      else
        echo "custom"
      fi
    else
      echo "baseline"               # P0 (no NetEm)
    fi
  else
    echo "baseline"
  fi
}

# Create organized folder structure
NETEM_PROFILE=$(get_netem_profile)
TEST_DIR="$OUTDIR/bytes_on_wire/${NETEM_PROFILE}"
CSV="${TEST_DIR}/bytes_on_wire_mac.csv"

# Clean and create test directory
rm -rf "$TEST_DIR" 2>/dev/null || true
mkdir -p "$TEST_DIR"

echo "==== Bytes-on-the-wire measurement (macOS, Organized Folder Structure) ===="
echo "📁 Test directory: $TEST_DIR"
echo "🌐 NetEm profile: $NETEM_PROFILE"
echo "⏱️  Duration: ${DURATION}s, Hits: ${HITS}, Drive: ${DRIVE}"
echo ""

require() { command -v "$1" >/dev/null 2>&1 || { echo "Missing: $1" >&2; exit 1; }; }
require tshark
require curl
require tcpdump

PORTS=("$@")
if [[ ${#PORTS[@]} -eq 0 ]]; then
  PORTS=(4431 4432 4434 4435)
fi

echo "port,clienthello_bytes,server_flight_bytes,server_records,total_handshake_bytes,total_records" > "$CSV"

capture_one() {
  local PORT=$1
  local PCAP="/tmp/byw_${PORT}.pcap"

  if [[ "$DRIVE" == "1" ]]; then
    echo "→ Port ${PORT}: zaczynam capture na lo0 (${DURATION}s) i odpalam ${HITS} żądań…"
  else
    echo "→ Port ${PORT}: zaczynam PASYWNY capture na lo0 (${DURATION}s) — wyzwól handshake po swojej stronie…"
  fi

  # start capture tcpdump na lo0 w tle (bez limitu czasu wbudowanego)
  sudo tcpdump -i lo0 -n -s0 -w "$PCAP" "tcp port ${PORT}" >/dev/null 2>&1 &
  local CAP_PID=$!
  # zaplanuj zakończenie po DURATION
  ( sleep "$DURATION"; kill "$CAP_PID" >/dev/null 2>&1 || true ) &
  local KILLER_PID=$!

  # opcjonalnie generuj ruch curl
  if [[ "$DRIVE" == "1" ]]; then
    for i in $(seq 1 "$HITS"); do
      curl -k --http1.1 --max-time 3 -s -o /dev/null "https://localhost:${PORT}/" || true
    done
  fi

  # poczekaj aż killer zakończy capture
  wait "$KILLER_PID" 2>/dev/null || true

  if [[ ! -s "$PCAP" ]]; then
    echo "⚠️  Port ${PORT}: brak PCAP lub pusty plik — pomijam."
    return
  fi

  # Wymuś dekoder TLS na porcie
  local DOPT=(-d "tcp.port==${PORT},tls")

  # Agreguj po tcp.stream, aby nie mieszać ramek z różnych połączeń
  local CH_SUM=0
  local S_FLIGHT_SUM=0
  local S_RECS_SUM=0
  local TOTAL_SUM=0
  local TOTAL_RECS_SUM=0

  local STREAMS
  STREAMS=$(tshark "${DOPT[@]}" -r "$PCAP" -Y "tcp.port==${PORT} && tcp.stream >= 0" -T fields -e tcp.stream 2>/dev/null | sort -n | uniq)
  if [[ -z "${STREAMS}" ]]; then
    echo "⚠️  Port ${PORT}: brak tcp.stream — pomijam."
  fi

  for S in ${STREAMS}; do
    # ClientHello bytes w danym streamie
    local CH_BYTES
    CH_BYTES=$(tshark "${DOPT[@]}" -r "$PCAP" \
               -Y "tcp.stream==${S} && tcp.dstport==${PORT} && tls.handshake.type==1" \
               -T fields -e tls.handshake.length 2>/dev/null | awk '{s+=$1} END{print s+0}')

    # Pierwsza ramka Application Data od klienta w tym streamie
    local FIRST
    FIRST=$(tshark "${DOPT[@]}" -r "$PCAP" \
            -Y "tcp.stream==${S} && tcp.dstport==${PORT} && tls.record.content_type==23" \
            -T fields -e frame.number 2>/dev/null | head -n1)
    [[ -z "$FIRST" ]] && FIRST=999999999

    # Server→client flight do FIRST
    local S_FLIGHT S_RECS
    S_FLIGHT=$(tshark "${DOPT[@]}" -r "$PCAP" \
               -Y "tcp.stream==${S} && tcp.srcport==${PORT} && frame.number <= ${FIRST} && tls.record.length" \
               -T fields -e tls.record.length 2>/dev/null | awk '{s+=$1} END{print s+0}')
    S_RECS=$(tshark "${DOPT[@]}" -r "$PCAP" \
             -Y "tcp.stream==${S} && tcp.srcport==${PORT} && frame.number <= ${FIRST} && tls.record.length" \
             -T fields -e tls.record.length 2>/dev/null | wc -l | awk '{print $1}')

    # Obie strony do FIRST
    local TOTAL TOTAL_RECS
    TOTAL=$(tshark "${DOPT[@]}" -r "$PCAP" \
            -Y "tcp.stream==${S} && frame.number <= ${FIRST} && tls.record.length" \
            -T fields -e tls.record.length 2>/dev/null | awk '{s+=$1} END{print s+0}')
    TOTAL_RECS=$(tshark "${DOPT[@]}" -r "$PCAP" \
                 -Y "tcp.stream==${S} && frame.number <= ${FIRST} && tls.record.length" \
                 -T fields -e tls.record.length 2>/dev/null | wc -l | awk '{print $1}')

    CH_SUM=$((CH_SUM + CH_BYTES))
    S_FLIGHT_SUM=$((S_FLIGHT_SUM + S_FLIGHT))
    S_RECS_SUM=$((S_RECS_SUM + S_RECS))
    TOTAL_SUM=$((TOTAL_SUM + TOTAL))
    TOTAL_RECS_SUM=$((TOTAL_RECS_SUM + TOTAL_RECS))
  done

  echo "${PORT},${CH_SUM},${S_FLIGHT_SUM},${S_RECS_SUM},${TOTAL_SUM},${TOTAL_RECS_SUM}" >> "$CSV"
  echo "✓ Port ${PORT}: CH=${CH_SUM}B, Sflight=${S_FLIGHT_SUM}B, Total=${TOTAL_SUM}B"
}

for p in "${PORTS[@]}"; do
  capture_one "$p"
done

echo "✅ Bytes-on-the-wire measurement completed"
echo "📁 Results saved in: $TEST_DIR/"
echo "📊 CSV file: $CSV"