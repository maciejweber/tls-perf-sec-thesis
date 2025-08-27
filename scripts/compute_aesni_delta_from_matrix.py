#!/usr/bin/env python3
import argparse
import json
from pathlib import Path
import re
import csv

parser = argparse.ArgumentParser(
    description="Compute AES-NI delta% from run_matrix directory"
)
parser.add_argument("run_dir", help="Path to results/run_matrix_<TS> directory")
args = parser.parse_args()

RUN_DIR = Path(args.run_dir).resolve()
AES_ON = RUN_DIR / "aes_on"
AES_OFF = RUN_DIR / "aes_off"
PROFILES = ["P0", "P1", "P2", "P3"]

IMPL_BY_PORT = {
    4431: "openssl",
    4432: "openssl",
    8443: "openssl",
    4434: "wolfssl",
    4435: "wolfssl",
    11112: "wolfssl",
}

rows = []

# Handshake: files like handshake_<port>_s33_on.json and _off.json
for prof in PROFILES:
    d_on = AES_ON / prof / "handshake"
    d_off = AES_OFF / prof / "handshake"
    if not (d_on.exists() and d_off.exists()):
        continue
    for port in [4431, 4432, 8443, 4434, 4435, 11112]:
        f_on = d_on / f"handshake_{port}_s33_on.json"
        f_off = d_off / f"handshake_{port}_s33_off.json"
        if not (f_on.exists() and f_off.exists()):
            # Also try without s33 in name (fallback)
            f_on2 = next(d_on.glob(f"handshake_{port}_*_on.json"), None)
            f_off2 = next(d_off.glob(f"handshake_{port}_*_off.json"), None)
            if f_on2 and f_off2:
                f_on, f_off = f_on2, f_off2
            else:
                continue
        try:
            on_v = json.loads(f_on.read_text()).get("mean_ms")
            off_v = json.loads(f_off.read_text()).get("mean_ms")
            if on_v and off_v and on_v != 0:
                delta = (off_v - on_v) / on_v * 100.0
                rows.append(
                    {
                        "metric": "handshake_ms",
                        "profile": prof,
                        "payload_mb": "",
                        "concurrency": "",
                        "implementation": IMPL_BY_PORT.get(port, "unknown"),
                        "port": port,
                        "on_value": on_v,
                        "off_value": off_v,
                        "delta_percent": delta,
                    }
                )
        except Exception:
            pass

# Bulk: path <P>/bulk/p<payload>_c<conc>/bulk_<port>_r64_p<p>_c<c>_<on|off>.json
payloads = ["0.1", "1", "10"]
concs = ["1", "8", "32"]
for prof in PROFILES:
    for p in payloads:
        for c in concs:
            d_on = AES_ON / prof / "bulk" / f"p{p}_c{c}"
            d_off = AES_OFF / prof / "bulk" / f"p{p}_c{c}"
            if not (d_on.exists() and d_off.exists()):
                continue
            for port in [4431, 4432, 8443, 4434, 4435, 11112]:
                f_on = d_on / f"bulk_{port}_r64_p{p}_c{c}_on.json"
                f_off = d_off / f"bulk_{port}_r64_p{p}_c{c}_off.json"
                if not (f_on.exists() and f_off.exists()):
                    continue
                try:
                    on = json.loads(f_on.read_text())
                    off = json.loads(f_off.read_text())
                    on_v = on.get("throughput_mb_s")
                    off_v = off.get("throughput_mb_s")
                    if on_v and off_v and on_v != 0:
                        delta = (off_v - on_v) / on_v * 100.0
                        rows.append(
                            {
                                "metric": "throughput_mb_s",
                                "profile": prof,
                                "payload_mb": p,
                                "concurrency": c,
                                "implementation": IMPL_BY_PORT.get(port, "unknown"),
                                "port": port,
                                "on_value": on_v,
                                "off_value": off_v,
                                "delta_percent": delta,
                            }
                        )
                except Exception:
                    pass

out_csv = RUN_DIR / "aesni_delta.csv"
with out_csv.open("w", newline="") as f:
    w = csv.DictWriter(
        f,
        fieldnames=[
            "metric",
            "profile",
            "payload_mb",
            "concurrency",
            "implementation",
            "port",
            "on_value",
            "off_value",
            "delta_percent",
        ],
    )
    w.writeheader()
    for r in rows:
        w.writerow(r)

print(f"Wrote {len(rows)} rows to {out_csv}")
