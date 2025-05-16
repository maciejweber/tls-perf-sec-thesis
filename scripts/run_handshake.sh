
#!/usr/bin/env bash

echo "==== Test wydajności handshake TLS ===="

HOST="localhost"  
PORTS=(4431 4432 4433)  
TEST_TIME=15  
OUTPUT_DIR="results"

mkdir -p $OUTPUT_DIR

for PORT in "${PORTS[@]}"; do
  echo ""
  echo "Testowanie ${HOST}:${PORT} (${TEST_TIME} sekund)"
  echo "Wymuszanie pełnego handshake (bez session resumption)"
  
  
  result=$(openssl s_time -connect ${HOST}:${PORT} -new -time ${TEST_TIME} 2>&1)
  
  if [[ $? -ne 0 ]]; then
    echo "Błąd podczas wykonywania testu dla portu ${PORT}:"
    echo "$result"
    continue
  fi
  
  
  total_connections=$(echo "$result" | grep "Processed" | awk '{print $2}')
  total_time=$(echo "$result" | grep "Processed" | awk '{print $5}')
  connections_per_sec=$(echo "$result" | grep "Processed" | awk '{print $8}')
  
  
  if [[ -n "$total_connections" && -n "$total_time" && "$total_connections" -gt 0 ]]; then
    mean_ms=$(echo "scale=4; 1000 * $total_time / $total_connections" | bc)
  else
    mean_ms="N/A"
    echo "Nie udało się obliczyć średniego czasu handshake."
  fi
  
  echo ""
  echo "Wyniki dla ${HOST}:${PORT}:"
  echo "* Liczba przeprowadzonych handshake'ów: $total_connections"
  echo "* Czas testu: $total_time s"
  echo "* Handshake'ów na sekundę: $connections_per_sec"
  echo "* Średni czas handshake: ${mean_ms} ms"
  
  
  echo "{\"port\": $PORT, \"mean_ms\": $mean_ms, \"total_connections\": $total_connections, \"connections_per_sec\": $connections_per_sec, \"test_time_s\": $total_time}" \
    > "${OUTPUT_DIR}/handshake_${PORT}.json"
  
  echo "Wyniki zapisane w ${OUTPUT_DIR}/handshake_${PORT}.json"
done

echo ""
echo "Wszystkie testy zakończone."