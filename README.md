# ReproBench – środowisko replikowalnych benchmarków kryptograficznych

Projekt demonstruje pełny cykl **eksperyment ➜ automatyczna replikacja**  
z wykorzystaniem kontenerów, CI/CD oraz hermetyzacji zależności.

## Szybki start

```bash
git clone https://github.com/your‑org/reprobench.git
cd reprobench
./bootstrap.sh
```

## Jak uruchomić eksperymenty i odtworzyć wykresy

### Wymagania

- Docker / Docker Compose
- macOS: `powermetrics` (systemowe), `bc`, `jq`
- Python 3.9+, `venv`

### 1) Certyfikaty i stack

```bash
# (opcjonalnie) generowanie certów demo
./scripts/gen-certs.sh

# start usług: nginx (OpenSSL+OQS) + backend-sink
docker compose up -d --build nginx-tls backend-sink
```

### 2) Pomiary

- Handshake (wszystkie porty):

```bash
./scripts/run_handshake.sh
```

- Przepustowość POST (rozmiar żądania w MB):

```bash
PAYLOAD_SIZE_MB=4 REQUESTS=50 ./scripts/run_bulk.sh
```

- 0‑RTT (resumption + early_data w MB):

```bash
EARLY_DATA_MB=8 ./scripts/run_0rtt.sh
```

- Bieg zbiorczy (iteracje, NetEm, pomiar zasobów):

```bash
ITERATIONS=5 SUITES='x25519_aesgcm chacha20 kyber_hybrid' TESTS='handshake bulk 0rtt' \
NETEM=0 MEASURE_RESOURCES=0 PAYLOAD_SIZE_MB=4 ./scripts/run_all.sh
```

- AES‑NI OFF (porównanie):

```bash
DISABLE_AESNI=1 ITERATIONS=5 REQUESTS=50 PAYLOAD_SIZE_MB=4 ./scripts/run_all.sh
```

Uwaga: wyniki JSON/CSV trafiają do `results/` oraz `results/run_YYYYMMDD_HHMMSS*`.

### 3) Analiza i wykresy

```bash
python3 -m venv .venv && . .venv/bin/activate && pip install pandas matplotlib seaborn
MPLBACKEND=Agg python3 analyze.py -r results/latest -s
```

Wykresy zapisują się w `figures/<run>/analyze`.

Porównanie AES‑NI ON vs OFF:

```bash
MPLBACKEND=Agg python3 compare_aesni.py results/run_<ON> results/run_<OFF>
```

Wyniki: `figures/<ON>/compare_aesni` oraz CSV `aesni_compare.csv` w katalogu biegu `<ON>`.

### 4) NetEm (symulacja sieci na macOS)

```bash
./scripts/netem_mac.sh 50 0.01   # delay=50ms, loss=1%
./scripts/netem_mac.sh clear
```

### Uwaga dla macOS (Docker Desktop)

Skrypty są uodpornione na brak `--network host`. Na macOS automatycznie używany jest host `host.docker.internal`, a po stronie `docker run` nie jest dodawana flaga `--network host`. Na Linuxie pozostaje dotychczasowe zachowanie z host networking.

## Dodatkowe skrypty (quick wins)

- Bytes on the wire:
  ```bash
  ./scripts/bytes_on_wire.sh            # zapisze results/bytes_on_wire.csv
  ```
- TTFB (mały payload, curl):
  ```bash
  ./scripts/run_ttfb.sh 4431            # zapisze results/ttfb_4431.json
  ```
- Sweep payload × concurrency (bulk):
  ```bash
  PAYLOADS="0.1 1 10" CONCURRENCIES="1 8 32" REQUESTS=64 ITERATIONS=1 \
  ./scripts/run_sweep.sh
  ```
