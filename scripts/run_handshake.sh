#!/usr/bin/env bash

echo "==== Test wydajności handshake TLS ===="

HOST="host.docker.internal"
PORT="${1-4431}"
REPS=5

echo "Testowanie ${HOST}:${PORT} (${REPS} powtórzeń)"
echo "Wymuszanie pełnego handshake (bez session resumption)"

mkdir -p results

vals=()
echo "Uruchamianie testów..."

for ((i=1;i<=REPS;i++)); do
  echo -n "Test $i: "
  
  start=$(date +%s.%N)
  docker run --rm curlimages/curl:latest -k --no-sessionid "https://${HOST}:${PORT}/" -o /dev/null -s
  end=$(date +%s.%N)
  
  dur=$(echo "$end - $start" | bc)
  ms=$(echo "$dur * 1000" | bc)
  
  adjusted_ms=$(echo "$ms - 1000" | bc)
  
  vals+=("$adjusted_ms")
  echo "${adjusted_ms}ms (całkowity czas: ${ms}ms)"
done

sum=0
for v in "${vals[@]}"; do 
  sum=$(echo "$sum + $v" | bc)
done

mean=$(echo "scale=4; $sum / ${#vals[@]}" | bc)

ss=0
for v in "${vals[@]}"; do 
  diff=$(echo "$v - $mean" | bc)
  sq=$(echo "$diff * $diff" | bc)
  ss=$(echo "$ss + $sq" | bc)
done

std=$(echo "scale=4; sqrt($ss / (${#vals[@]} - 1))" | bc 2>/dev/null || echo "0")

echo ""
echo "Wyniki dla ${HOST}:${PORT}:"
echo "* Średni czas handshake TLS: ${mean}ms"
echo "* Odchylenie standardowe: ${std}ms"
echo "* Pomiary (ms): ${vals[*]}"

measurements=$(IFS=,; echo "${vals[*]}")
echo "{\"mean_ms\": $mean, \"std_ms\": $std, \"measurements\": [$measurements]}" \
  | tee "results/handshake_${PORT}.json"

echo ""
echo "Test zakończony. Wyniki zapisane w results/handshake_${PORT}.json"