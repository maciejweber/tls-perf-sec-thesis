#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

HOST=localhost
if [[ "$(uname)" == "Darwin" ]]; then
  HOST="host.docker.internal"
fi

if [[ $# -eq 1 ]]; then
  PORTS=("$1")
else
  PORTS=(4431 4432 8443)
fi

OUTDIR="$ROOT_DIR/results"; mkdir -p "$OUTDIR"
CSV="$OUTDIR/bytes_on_wire.csv"
echo "port,mode,client_hello_bytes,server_flight_bytes,tls_records,total_tls_bytes" > "$CSV"

run_and_capture_full() {
  local port=$1
  docker exec tls-perf-nginx sh -lc "\
    /usr/local/bin/openssl s_client -msg -tls1_3 -CAfile /etc/nginx/certs/ca.pem -connect ${HOST}:${port} </dev/null 2>&1 | sed -n '1,240p'"
}

run_and_capture_0rtt() {
  local port=$1
  docker exec tls-perf-nginx sh -lc '
    ED=/tmp/ed_'"$port"'.bin; S=/tmp/sess_'"$port"'.bin
    # establish session
    if [ '"$port"' -eq 8443 ]; then
      /usr/local/bin/openssl s_client -quiet -tls1_3 -provider default -provider oqsprovider -groups X25519MLKEM768 -CAfile /etc/nginx/certs/ca.pem -sess_out "$S" -connect '"${HOST}"':'"$port"' </dev/null >/dev/null 2>&1 || true
    else
      /usr/local/bin/openssl s_client -quiet -tls1_3 -provider default -CAfile /etc/nginx/certs/ca.pem -sess_out "$S" -connect '"${HOST}"':'"$port"' </dev/null >/dev/null 2>&1 || true
    fi
    # prepare tiny early data (HTTP headers only)
    printf "POST /upload HTTP/1.1\r\nHost: %s\r\nContent-Length: 0\r\nConnection: close\r\n\r\n" '"${HOST}"' > "$ED"
    # resume with early data and verbose messages
    if [ '"$port"' -eq 8443 ]; then
      /usr/local/bin/openssl s_client -msg -tls1_3 -provider default -provider oqsprovider -groups X25519MLKEM768 -CAfile /etc/nginx/certs/ca.pem -sess_in "$S" -early_data "$ED" -connect '"${HOST}"':'"$port"' </dev/null 2>&1 | sed -n "1,240p"
    else
      /usr/local/bin/openssl s_client -msg -tls1_3 -provider default -CAfile /etc/nginx/certs/ca.pem -sess_in "$S" -early_data "$ED" -connect '"${HOST}"':'"$port"' </dev/null 2>&1 | sed -n "1,240p"
    fi'
}

parse_bytes() {
  awk '
    /\*\*\>\> / {next} # ignore headers if any
    /\[length/ {
      if (match($0,/\[length [0-9]+\]/)) {
        n=substr($0,RSTART+8,RLENGTH-9); gsub(/[^0-9]/, "", n);
        if ($0 ~ /^>>>/ && client_done==0) { cw+=n; cr++ } else { sw+=n; sr++ }
      }
    }
    /SSL handshake has read/ {client_done=1}
    END {printf "%d,%d,%d,%d\n", cw, sw, (cr+sr), (cw+sw)}
  '
}

echo "==== Bytes-on-the-wire TLS 1.3 (full handshake + 0-RTT) ===="
for PORT in "${PORTS[@]}"; do
  out_full=$(run_and_capture_full "$PORT" | parse_bytes)
  echo "$PORT,full,$out_full" >> "$CSV"
  echo "✓ port $PORT (full) -> $out_full"
  # 0-RTT capture (only for OpenSSL-based ports 4431,4432,8443)
  if [[ "$PORT" == "4431" || "$PORT" == "4432" || "$PORT" == "8443" ]]; then
    out_0rtt=$(run_and_capture_0rtt "$PORT" | parse_bytes || echo "0,0,0,0")
    echo "$PORT,0rtt,$out_0rtt" >> "$CSV"
    echo "✓ port $PORT (0rtt) -> $out_0rtt"
  fi
done

echo "✅ Saved $CSV" 