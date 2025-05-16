#!/usr/bin/env bash

echo "==== Prosty test wydajności TLS ===="
mkdir -p results

HOST="host.docker.internal"

test_port() {
  local port=$1
  local desc=$2
  local count=5

  echo "Testowanie $desc (port $port)..."

  total=0
  for i in $(seq 1 $count); do
    echo -n "  Test $i: "
    start=$(date +%s.%N)
    curl -k "https://${HOST}:${port}/" -o /dev/null -s
    end=$(date +%s.%N)
    time=$(echo "$end - $start" | bc -l)
    echo "${time}s"
    total=$(echo "$total + $time" | bc -l)
  done

  avg=$(echo "scale=6; $total / $count" | bc -l)
  avg=$(printf "%.6f" "$avg")        

  echo "Średni czas dla $desc: ${avg}s"

  echo "{\"config\": \"$desc\", \"avg_time\": $avg}" \
    > "results/simple_${port}.json"
}

test_port 4431 "AES-GCM z ECDSA P-256" && echo ""
test_port 4432 "ChaCha20-Poly1305 z ECDSA P-256" && echo ""
test_port 4433 "AES-256-GCM z Ed25519" && echo ""

echo "Testy zakończone. Wyniki zapisane w katalogu results/"
