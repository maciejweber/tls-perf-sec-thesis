# ReproBench – środowisko replikowalnych benchmarków kryptograficznych

Projekt demonstruje pełny cykl eksperyment ➜ automatyczna replikacja z wykorzystaniem kontenerów, CI/CD oraz hermetyzacji zależności.

## Szybki start

```bash
git clone https://github.com/your‑org/reprobench.git
cd reprobench
```

## Certyfikaty (ECDSA i RSA) – bez nadpisywania istniejących

Skrypt generuje łańcuch demo dla ECDSA P‑256 oraz RSA‑2048 (nazwy plików zawierają algorytm, np. ecdsa-p256.crt, rsa-2048.crt). Ponowne uruchomienie nadpisze pliki dla tego samego algorytmu (świadomie).

```bash
./scripts/gen-certs.sh
# Pliki trafiają do katalogu certs/ (np. certs/ecdsa-p256.crt, certs/rsa-2048.crt)
```

## Uruchomienie usług

```bash
docker compose up -d --build nginx-tls backend-sink wolf-server wolfssl-server-kyber lighttpd-wolfssl
```

- Porty (przykłady):
  - OpenSSL/nginx: 4431 (X25519+AES‑GCM), 4432 (X25519+ChaCha20), 8443 (X25519+ML‑KEM‑768 hybryda)
  - wolfSSL/lighttpd: 4434 (AES‑GCM), 4435 (ChaCha20)
  - wolfSSL example (hybryda): 11112 (X25519+ML‑KEM‑768)

## Jak uruchomić wszystkie skrypty (tylko dane)

Poniżej minimalne komendy do zebrania danych. Pliki wynikowe zapisują się w `results/` oraz w katalogach biegów `results/run_YYYYMMDD_HHMMSS*` (gdy używasz `run_all.sh`).

### 1) Handshake latency

```bash
# Wszystkie porty
SAMPLES=20 ./scripts/run_handshake.sh
# Wybrany port
SAMPLES=20 ./scripts/run_handshake.sh 4431
# Wyniki: results/handshake_<port>_s<SAMPLES>.json
```

### 2) Bulk throughput (POST)

```bash
# Wszystkie porty
REQUESTS=50 PAYLOAD_SIZE_MB=1 CONCURRENCY=1 ./scripts/run_bulk.sh
# Wybrany port i większy payload + równoległość
REQUESTS=64 PAYLOAD_SIZE_MB=10 CONCURRENCY=8 ./scripts/run_bulk.sh 4432
# Wyniki: results/bulk_<port>_r<REQUESTS>_p<PAYLOAD_SIZE_MB>_c<CONCURRENCY>.json
# Surowe czasy per‑request: results/raw/bulk_<port>.txt
```

### 3) 0‑RTT (resumption + early data)

```bash
# Wszystkie porty (dla nginx‑TLS: 4431/4432/8443)
EARLY_DATA_MB=1 COUNT=10 ./scripts/run_0rtt.sh
# Wybrany port
EARLY_DATA_MB=1 COUNT=10 ./scripts/run_0rtt.sh 8443
# Wyniki: results/simple_<port>_ed<EARLY_DATA_MB>_n<COUNT>.json
```

### 4) Full handshake + POST (bez resumption)

```bash
# Wybrany port (np. klasyczny AES)
EARLY_DATA_MB=1 COUNT=5 ./scripts/run_full_post.sh 4431
# Wyniki: results/fullpost_<port>_mb<EARLY_DATA_MB>_n<COUNT>.json
```

### 5) TTFB (curl)

```bash
TTFB_PAYLOAD_KB=16 ./scripts/run_ttfb.sh 4431
# Wyniki: results/ttfb_<port>_kb<TTFB_PAYLOAD_KB>.json
```

### 6) Bytes on the wire (TLS 1.3 handshake)

```bash
brew install wireshark                # dostarcza tshark
sudo ./scripts/bytes_on_wire_mac.sh  # klasyczne porty: 4431/4432/4434/4435
sudo ./scripts/bytes_on_wire_mac.sh 4431 4432  # własne porty
# Wynik: results/bytes_on_wire_mac.csv (kolumny: port, clienthello_bytes, server_flight_bytes, server_records, total_handshake_bytes, total_records)
```

Klasyczne bytes‑on‑the‑wire mierzymy na macOS powyższym skryptem. PQ prezentujemy jako handshake_ms/TTFB i Δ% throughput (różnice w bajtach są implikowane przez wyniki czasowe i literaturę). Progiem końca handshaku jest pierwszy Application Data od klienta.

### 7) NetEm (symulacja sieci na macOS)

```bash
# Profile P0–P3
./scripts/netem_profiles.sh P0   # 0 ms, 0%
./scripts/netem_profiles.sh P1   # 50 ms, jitter nominal (macOS ignoruje jitter)
./scripts/netem_profiles.sh P2   # 50 ms, 0.5% loss
./scripts/netem_profiles.sh P3   # 100 ms, 0%
# Wyczyszczenie
./scripts/netem_profiles.sh clear
```

### 8) Bieg zbiorczy (opcjonalnie) — lub pełna macierz profili/payload/concurrency

```bash
ITERATIONS=5 \
SUITES='x25519_aesgcm chacha20 kyber_hybrid' \
TESTS='handshake bulk 0rtt' \
NETEM=0 MEASURE_RESOURCES=0 PAYLOAD_SIZE_MB=1 \
./scripts/run_all.sh
# Wyniki: results/run_YYYYMMDD_HHMMSS*/ (bench.csv, kopie JSONów z results/, config.txt)

# Pełna macierz profili P0–P3 × payload × concurrency z AES-NI ON/OFF:
PAYLOADS="0.1 1 10" CONCURRENCIES="1 8 32" PROFILES="P0 P2 P3" \
REQUESTS=64 SAMPLES=33 COUNT_0RTT=10 DO_0RTT=1 \
./scripts/run_matrix.sh
# Wyniki: results/run_matrix_<TS>/aes_<on|off>/<P0|P1|P2|P3>/{handshake,bulk,0rtt}/...
```

## Gdzie trafiają wyniki

- `results/handshake_<port>_s<SAMPLES>.json`
- `results/bulk_<port>_r<REQUESTS>_p<PAYLOAD_SIZE_MB>_c<CONCURRENCY>.json`
- `results/simple_<port>_ed<EARLY_DATA_MB>_n<COUNT>.json`
- `results/fullpost_<port>_mb<EARLY_DATA_MB>_n<COUNT>.json`
- `results/ttfb_<port>_kb<TTFB_PAYLOAD_KB>.json`
- `results/bytes_on_wire_mac.csv`
- Surowe czasy per‑request (bulk): `results/raw/bulk_<port>.txt`
- Zbiorczy bieg: `results/run_YYYYMMDD_HHMMSS*/` (w tym `bench.csv` i kopie plików JSON)

Uwaga: porty hybrydowe wolfSSL w tym repo to 11112 (example server). Jeśli używasz innego portu hybrydy (np. 9443), dostosuj komendy do swojej konfiguracji.
