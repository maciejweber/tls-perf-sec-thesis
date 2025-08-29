#!/usr/bin/env python3
"""
Skrypt do generowania wykresów TLS Performance & Security Analysis
Zgodny ze specyfikacją 12 wykresów dla thesis
"""

import json
import csv
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
import re
from typing import Dict, List, Tuple, Optional

# Konfiguracja
plt.style.use("seaborn-v0_8")
plt.rcParams["figure.figsize"] = (12, 8)
plt.rcParams["font.size"] = 10
plt.rcParams["axes.grid"] = True
plt.rcParams["grid.alpha"] = 0.3

# Kolory i style
COLORS = {
    "aes_on": "#2E86AB",
    "aes_off": "#A23B72",
    "delta": "#F18F01",
    "hybrid": "#C73E1D",
    "openssl": "#1f77b4",  # Blue
    "wolfssl": "#ff7f0e",  # Orange
}

# Ujednolicona kolejność portów
PORT_ORDER = [4431, 4432, 8443, 4434, 4435, 11112]


# Mapowanie portów na implementacje i kolory
def get_port_color(port):
    if port in [4431, 4432, 8443]:
        return COLORS["openssl"]
    else:
        return COLORS["wolfssl"]


# Mapowanie portów na nazwy
PORT_NAMES = {
    4431: "4431\nAES-GCM",
    4432: "4432\nChaCha20",
    8443: "8443\nHybrid\nMLKEM768",
    4434: "4434\nwolfSSL\nAES-GCM",
    4435: "4435\nwolfSSL\nChaCha20",
    11112: "11112\nwolfSSL\nPQ-KEM",
}

OPENSSL_PORTS = [4431, 4432, 8443]
HTTP_PORTS = [4431, 4432, 8443, 4434, 4435]  # Bez 11112


def load_json_data(filepath: Path) -> Optional[Dict]:
    """Ładuje dane JSON z obsługą błędów"""
    try:
        with open(filepath, "r") as f:
            return json.load(f)
    except Exception as e:
        print(f"Błąd ładowania {filepath}: {e}")
        return None


def calculate_percentiles(
    data: List[float],
) -> Tuple[float, float, float, float, float]:
    """Oblicza percentyle: p25, p50, p75, p95, IQR"""
    data_ms = [x * 1000 for x in data]  # Konwersja s -> ms
    p25, p50, p75, p95 = np.percentile(data_ms, [25, 50, 75, 95])
    iqr = p75 - p25
    return p25, p50, p75, p95, iqr


def load_handshake_data(base_path: Path, aes_mode: str, ports: List[int]) -> Dict:
    """Ładuje dane handshake dla danego trybu AES"""
    data = {}
    folder = base_path / f"handshake/baseline_aes_{aes_mode}_s33"

    for port in ports:
        filepath = folder / f"handshake_{port}_s33.json"
        json_data = load_json_data(filepath)
        if json_data and "raw_measurements" in json_data:
            raw_data = json_data["raw_measurements"]
            p25, p50, p75, p95, iqr = calculate_percentiles(raw_data)
            data[port] = {
                "p25": p25,
                "p50": p50,
                "p75": p75,
                "p95": p95,
                "iqr": iqr,
                "raw": [x * 1000 for x in raw_data],  # ms
                "algorithm": json_data.get("algorithm", f"Port {port}"),
            }
    return data


def load_ttfb_data(base_path: Path, ports: List[int]) -> Dict:
    """Ładuje dane TTFB"""
    data = {}
    folder = base_path / "ttfb/baseline_kb1"

    for port in ports:
        filepath = folder / f"ttfb_{port}.json"
        json_data = load_json_data(filepath)
        if json_data and "ttfb_s" in json_data:
            ttfb_ms = json_data["ttfb_s"] * 1000
            data[port] = {"ttfb_ms": ttfb_ms}
    return data


def load_throughput_data(
    base_path: Path, aes_mode: str, payload_mb: int, concurrency: int, ports: List[int]
) -> Dict:
    """Ładuje dane throughput"""
    data = {}
    folder = (
        base_path / f"bulk/baseline_aes_{aes_mode}_r64_p{payload_mb}_c{concurrency}"
    )

    for port in ports:
        filepath = folder / f"bulk_{port}_r64_p{payload_mb}_c{concurrency}.json"
        json_data = load_json_data(filepath)
        if json_data and "throughput_mb_s" in json_data:
            data[port] = {
                "throughput_mb_s": json_data["throughput_mb_s"],
                "avg_request_time_s": json_data.get("avg_request_time_s", 0),
            }
    return data


def load_0rtt_data(base_path: Path, early_data_mb: float, ports: List[int]) -> Dict:
    """Ładuje dane 0-RTT"""
    data = {}
    folder = base_path / f"0rtt/baseline_aes_on_ed{early_data_mb}_n10"

    for port in ports:
        filepath = folder / f"simple_{port}_ed{early_data_mb}_n10.json"
        json_data = load_json_data(filepath)
        if json_data and "avg_time" in json_data:
            data[port] = {"avg_time_s": json_data["avg_time"]}
    return data


def load_full_post_data(base_path: Path, payload_mb: float, ports: List[int]) -> Dict:
    """Ładuje dane Full POST"""
    data = {}
    # Skrypt wygenerował dane dla 8MB, nie 1MB
    folder = base_path / f"full_post/baseline_aes_on_mb8_n3"

    for port in ports:
        # Użyj właściwej nazwy pliku: fullpost_4431.json
        filepath = folder / f"fullpost_{port}.json"
        json_data = load_json_data(filepath)
        if json_data and "avg_time" in json_data:
            data[port] = {"avg_time_s": json_data["avg_time"]}
    return data


def load_bytes_on_wire_data(base_path: Path) -> Dict:
    """Ładuje dane bytes-on-wire"""
    data = {}
    filepath = base_path / "bytes_on_wire/baseline/bytes_on_wire_mac.csv"

    try:
        with open(filepath, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row["port"]:  # Sprawdź czy wiersz nie jest pusty
                    port = int(row["port"])
                    data[port] = {
                        "clienthello_bytes": int(row["clienthello_bytes"]),
                        "server_flight_bytes": int(row["server_flight_bytes"]),
                        "total_handshake_bytes": int(row["total_handshake_bytes"]),
                        "total_records": int(row["total_records"]),
                    }
    except Exception as e:
        print(f"Błąd ładowania bytes-on-wire: {e}")

    return data


def parse_openssl_speed(filepath: Path) -> float:
    """Parsuje wyniki OpenSSL speed test"""
    try:
        with open(filepath, "r") as f:
            lines = f.readlines()

        for line in lines:
            if "AES-128-GCM" in line:
                # Extracting 16384 bytes column (last column)
                parts = line.split()
                if len(parts) >= 7:
                    speed_str = parts[-1].replace("k", "")
                    speed_kbps = float(speed_str)
                    speed_mbps = speed_kbps / 1024  # Convert k bytes/s to MB/s
                    return speed_mbps
    except Exception as e:
        print(f"Błąd parsowania OpenSSL speed: {e}")

    return 0.0


# === GENEROWANIE WYKRESÓW ===


def fig01_handshake_latency_aes_on(base_path: Path, output_dir: Path):
    """Fig.01 — Handshake latency p50/p95 per port (AES-ON)"""
    print("\n🔍 Fig.01 - Analiza danych Handshake Latency (AES-ON):")
    print("Typ wykresu: Słupkowy (bar chart) z p50 + whiskers dla p95")

    all_ports = [4431, 4432, 8443, 4434, 4435, 11112]
    data = load_handshake_data(base_path, "on", all_ports)

    if not data:
        print("❌ Brak danych dla Fig.01")
        return

    print(f"Załadowano dane dla portów: {sorted(data.keys())}")
    print("\n📊 Dane na wykresie (handshake latency):")
    print("Format: Port | p50 [ms] | p95 [ms] | IQR [ms] | Samples")
    for port in sorted(data.keys()):
        d = data[port]
        print(
            f"Port {port}: {d['p50']:.1f} | {d['p95']:.1f} | {d['iqr']:.1f} | {len(d['raw'])} samples"
        )
        print(f"  Algorithm: {d['algorithm']}")

    # Użyj ujednoliconej kolejności portów i kolorów OpenSSL vs wolfSSL
    ports = [p for p in PORT_ORDER if p in data]
    p50_values = [data[p]["p50"] for p in ports]
    p95_values = [data[p]["p95"] for p in ports]
    iqr_values = [data[p]["iqr"] for p in ports]
    port_colors = [get_port_color(port) for port in ports]

    fig, ax = plt.subplots(figsize=(12, 8))

    x = range(len(ports))
    bars = ax.bar(x, p50_values, color=port_colors, alpha=0.7, label="p50 (median)")

    # Dodaj p95 jako whiskers
    for i, (p50, p95) in enumerate(zip(p50_values, p95_values)):
        ax.plot([i, i], [p50, p95], "k-", linewidth=2)
        ax.plot([i - 0.1, i + 0.1], [p95, p95], "k-", linewidth=2)
        ax.text(i, p95 + 1, f"p95: {p95:.1f}", ha="center", va="bottom", fontsize=9)

    # Dodaj IQR w tooltipie/tekście
    for i, (port, iqr) in enumerate(zip(ports, iqr_values)):
        ax.text(
            i,
            p50_values[i] / 2,
            f"IQR: {iqr:.1f}",
            ha="center",
            va="center",
            fontsize=8,
            bbox=dict(boxstyle="round,pad=0.3", facecolor="white", alpha=0.8),
        )

    ax.set_xlabel("Port / Cipher Suite")
    ax.set_ylabel("Handshake Latency [ms]")
    ax.set_title(
        "Fig.01 — Handshake Latency p50/p95 per Port (AES-ON)",
        fontsize=14,
        fontweight="bold",
    )
    ax.set_xticks(x)
    ax.set_xticklabels([PORT_NAMES[p] for p in ports])
    ax.legend()
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(
        output_dir / "fig01_handshake_latency_aes_on.png", dpi=300, bbox_inches="tight"
    )
    plt.close()
    print("✅ Fig.01 wygenerowany")


def fig02_handshake_aes_off_delta(base_path: Path, output_dir: Path):
    """Fig.02 — Handshake AES-OFF: delta vs AES-ON"""
    print("\n🔍 Fig.02 - Analiza danych Handshake AES-OFF Delta:")
    print("Typ wykresu: Słupkowy (bar chart) z % zmianą")

    data_on = load_handshake_data(base_path, "on", OPENSSL_PORTS)
    data_off = load_handshake_data(base_path, "off", OPENSSL_PORTS)

    if not data_on or not data_off:
        print("❌ Brak danych dla Fig.02")
        return

    print(f"Porty OpenSSL: {OPENSSL_PORTS}")
    print(f"Dane AES-ON: {sorted(data_on.keys())}")
    print(f"Dane AES-OFF: {sorted(data_off.keys())}")

    print("\n📊 Dane na wykresie (AES-OFF vs AES-ON delta):")
    print("Format: Port | AES-ON p50 [ms] | AES-OFF p50 [ms] | Delta [%]")

    ports = sorted(set(data_on.keys()) & set(data_off.keys()))
    deltas = []

    for port in ports:
        p50_on = data_on[port]["p50"]
        p50_off = data_off[port]["p50"]
        delta_pct = ((p50_off / p50_on) - 1) * 100
        deltas.append(delta_pct)
        print(f"Port {port}: {p50_on:.1f} | {p50_off:.1f} | {delta_pct:+.1f}%")

    fig, ax = plt.subplots(figsize=(10, 6))

    x = range(len(ports))
    bars = ax.bar(x, deltas, color=COLORS["delta"], alpha=0.8)

    # Dodaj wartości na słupkach
    for i, delta in enumerate(deltas):
        ax.text(
            i,
            delta + 0.5 if delta >= 0 else delta - 0.5,
            f"{delta:+.1f}%",
            ha="center",
            va="bottom" if delta >= 0 else "top",
            fontweight="bold",
        )

    ax.set_xlabel("Port (OpenSSL only)")
    ax.set_ylabel("Change [%]")
    ax.set_title(
        "Fig.02 — Handshake AES-OFF: Delta vs AES-ON", fontsize=14, fontweight="bold"
    )
    ax.set_xticks(x)
    ax.set_xticklabels([PORT_NAMES[p] for p in ports])
    ax.axhline(y=0, color="black", linestyle="-", alpha=0.3)
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(
        output_dir / "fig02_handshake_aes_off_delta.png", dpi=300, bbox_inches="tight"
    )
    plt.close()
    print("✅ Fig.02 wygenerowany")


def fig03_cdf_handshake_aes_on(base_path: Path, output_dir: Path):
    """Fig.03 — CDF czasu handshaku (AES-ON)"""
    print("\n🔍 Fig.03 - Analiza danych CDF Handshake:")
    print("Typ wykresu: Liniowy (CDF) - rozkład kumulatywny")

    selected_ports = [4431, 4432, 8443]
    data = load_handshake_data(base_path, "on", selected_ports)

    if not data:
        print("❌ Brak danych dla Fig.03")
        return

    print(f"Wybrane porty: {selected_ports}")
    print("\n📊 Dane na wykresie (raw measurements dla CDF):")
    print("Format: Port | Min[ms] | Max[ms] | Samples | Raw Data Preview")
    for port in selected_ports:
        if port in data:
            raw_data = data[port]["raw"]
            print(
                f"Port {port}: {min(raw_data):.1f} | {max(raw_data):.1f} | {len(raw_data)} | {raw_data[:5]}..."
            )

    fig, ax = plt.subplots(figsize=(10, 6))

    for i, port in enumerate(selected_ports):
        if port in data:
            raw_data = sorted(data[port]["raw"])
            n = len(raw_data)
            y = np.arange(1, n + 1) / n

            # Użyj kolorów OpenSSL vs wolfSSL i dodaj cipher do legendy
            cipher_name = PORT_NAMES[port].replace("\n", " ")
            ax.plot(
                raw_data, y, label=cipher_name, linewidth=2, color=get_port_color(port)
            )

    ax.set_xlabel("Handshake Time [ms]")
    ax.set_ylabel("F(x) - Cumulative Probability")
    ax.set_title(
        "Fig.03 — CDF of Handshake Time (AES-ON)", fontsize=14, fontweight="bold"
    )
    ax.legend()
    ax.grid(True, alpha=0.3)
    ax.set_xlim(left=0)
    ax.set_ylim(0, 1)

    plt.tight_layout()
    plt.savefig(
        output_dir / "fig03_cdf_handshake_aes_on.png", dpi=300, bbox_inches="tight"
    )
    plt.close()
    print("✅ Fig.03 wygenerowany")


def fig04_ttfb_per_port(base_path: Path, output_dir: Path):
    """Fig.04 — TTFB p50/p95 per port (P0)"""
    print("\n🔍 Fig.04 - Analiza danych TTFB:")
    print("Typ wykresu: Słupkowy (bar chart) z TTFB per port")

    data = load_ttfb_data(base_path, HTTP_PORTS)

    if not data:
        print("❌ Brak danych dla Fig.04")
        return

    print(f"Porty HTTP: {HTTP_PORTS}")
    print(f"Znalezione dane: {sorted(data.keys())}")
    print("\n📊 Dane na wykresie (TTFB):")
    print("Format: Port | TTFB[ms]")
    for port in sorted(data.keys()):
        ttfb_ms = data[port]["ttfb_ms"]
        print(f"Port {port}: {ttfb_ms:.2f}ms")

    ports = sorted(data.keys())
    ttfb_values = [data[p]["ttfb_ms"] for p in ports]

    fig, ax = plt.subplots(figsize=(10, 6))

    x = range(len(ports))
    bars = ax.bar(x, ttfb_values, color=COLORS["aes_on"], alpha=0.7)

    # Dodaj wartości na słupkach
    for i, ttfb in enumerate(ttfb_values):
        ax.text(
            i, ttfb + 0.2, f"{ttfb:.1f}ms", ha="center", va="bottom", fontweight="bold"
        )

    ax.set_xlabel("Port")
    ax.set_ylabel("TTFB [ms]")
    ax.set_title("Fig.04 — TTFB per Port (P0)", fontsize=14, fontweight="bold")
    ax.set_xticks(x)
    ax.set_xticklabels([PORT_NAMES[p] for p in ports])
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(output_dir / "fig04_ttfb_per_port.png", dpi=300, bbox_inches="tight")
    plt.close()
    print("✅ Fig.04 wygenerowany")


def fig05_throughput_vs_concurrency(base_path: Path, output_dir: Path):
    """Fig.05 — Throughput vs concurrency (10 MB)"""
    print("\n🔍 Fig.05 - Analiza danych Throughput vs Concurrency:")
    print("Typ wykresu: Liniowy (line plot) - skalowanie concurrency")

    concurrencies = [8, 32]
    all_data = {}

    print(f"Concurrency levels: {concurrencies}")
    print(f"Payload: 10 MB")

    for conc in concurrencies:
        data = load_throughput_data(base_path, "on", 10, conc, HTTP_PORTS)
        all_data[conc] = data
        print(f"  Concurrency {conc}: {len(data)} portów załadowanych")

    if not all_data:
        print("❌ Brak danych dla Fig.05")
        return

    print("\n📊 Dane na wykresie (throughput scaling):")
    print("Format: Port | c=8[MB/s] | c=32[MB/s] | Scaling Ratio")
    for port in HTTP_PORTS:
        thr_8 = all_data[8].get(port, {}).get("throughput_mb_s", 0)
        thr_32 = all_data[32].get(port, {}).get("throughput_mb_s", 0)
        ratio = thr_32 / thr_8 if thr_8 > 0 else 0
        print(f"Port {port}: {thr_8:.1f} | {thr_32:.1f} | {ratio:.2f}x")

    fig, ax = plt.subplots(figsize=(10, 6))

    colors = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd"]

    for i, port in enumerate(HTTP_PORTS):
        throughputs = []
        for conc in concurrencies:
            if port in all_data[conc]:
                throughputs.append(all_data[conc][port]["throughput_mb_s"])
            else:
                throughputs.append(0)

        if any(t > 0 for t in throughputs):
            ax.plot(
                concurrencies,
                throughputs,
                "o-",
                label=PORT_NAMES[port],
                linewidth=2,
                markersize=8,
                color=colors[i],
            )

    ax.set_xlabel("Concurrency")
    ax.set_ylabel("Throughput [MB/s]")
    ax.set_title(
        "Fig.05 — Throughput vs Concurrency (10 MB payload)",
        fontsize=14,
        fontweight="bold",
    )
    ax.legend()
    ax.grid(True, alpha=0.3)
    ax.set_xticks(concurrencies)

    plt.tight_layout()
    plt.savefig(
        output_dir / "fig05_throughput_vs_concurrency.png", dpi=300, bbox_inches="tight"
    )
    plt.close()
    print("✅ Fig.05 wygenerowany")


def fig06_throughput_payload_size(base_path: Path, output_dir: Path):
    """Fig.06 — Throughput: wpływ wielkości payloadu (c=32)"""
    print("\n🔍 Fig.06 - Analiza danych Payload Size Impact:")
    print("Typ wykresu: Słupkowy (bar chart) - porównanie 1MB vs 10MB")

    data_1mb = load_throughput_data(base_path, "on", 1, 32, HTTP_PORTS)
    data_10mb = load_throughput_data(base_path, "on", 10, 32, HTTP_PORTS)

    if not data_1mb or not data_10mb:
        print("❌ Brak danych dla Fig.06")
        return

    print(f"Payloads: 1MB vs 10MB, Concurrency: 32")
    print(f"Dane 1MB: {len(data_1mb)} portów")
    print(f"Dane 10MB: {len(data_10mb)} portów")

    print("\n📊 Dane na wykresie (payload impact):")
    print("Format: Port | 1MB[MB/s] | 10MB[MB/s] | Gain Ratio")

    ports = sorted(set(data_1mb.keys()) & set(data_10mb.keys()))
    for port in ports:
        thr_1mb = data_1mb[port]["throughput_mb_s"]
        thr_10mb = data_10mb[port]["throughput_mb_s"]
        gain = thr_10mb / thr_1mb if thr_1mb > 0 else 0
        print(f"Port {port}: {thr_1mb:.1f} | {thr_10mb:.1f} | {gain:.2f}x")

    ports = sorted(set(data_1mb.keys()) & set(data_10mb.keys()))

    fig, ax = plt.subplots(figsize=(12, 6))

    x = np.arange(len(ports))
    width = 0.35

    throughput_1mb = [data_1mb[p]["throughput_mb_s"] for p in ports]
    throughput_10mb = [data_10mb[p]["throughput_mb_s"] for p in ports]

    bars1 = ax.bar(
        x - width / 2,
        throughput_1mb,
        width,
        label="1 MB",
        color=COLORS["aes_on"],
        alpha=0.7,
    )
    bars2 = ax.bar(
        x + width / 2,
        throughput_10mb,
        width,
        label="10 MB",
        color=COLORS["aes_off"],
        alpha=0.7,
    )

    # Dodaj wartości na słupkach
    for i, (t1, t10) in enumerate(zip(throughput_1mb, throughput_10mb)):
        ax.text(
            i - width / 2, t1 + 0.5, f"{t1:.1f}", ha="center", va="bottom", fontsize=9
        )
        ax.text(
            i + width / 2, t10 + 0.5, f"{t10:.1f}", ha="center", va="bottom", fontsize=9
        )

    ax.set_xlabel("Port")
    ax.set_ylabel("Throughput [MB/s]")
    ax.set_title(
        "Fig.06 — Throughput: Payload Size Impact (c=32)",
        fontsize=14,
        fontweight="bold",
    )
    ax.set_xticks(x)
    ax.set_xticklabels([PORT_NAMES[p] for p in ports])
    ax.legend()
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(
        output_dir / "fig06_throughput_payload_size.png", dpi=300, bbox_inches="tight"
    )
    plt.close()
    print("✅ Fig.06 wygenerowany")


def fig07_throughput_aes_off_delta(base_path: Path, output_dir: Path):
    """Fig.07 — Throughput AES-OFF delta (10 MB, c=32)"""
    print("\n🔍 Fig.07 - Analiza danych AES-OFF Throughput Delta:")
    print("Typ wykresu: Słupkowy (bar chart) z % zmianą dla AES-OFF")

    data_on = load_throughput_data(base_path, "on", 10, 32, OPENSSL_PORTS)
    data_off = load_throughput_data(base_path, "off", 10, 32, OPENSSL_PORTS)

    if not data_on or not data_off:
        print("❌ Brak danych dla Fig.07")
        return

    print(f"Porty OpenSSL: {OPENSSL_PORTS}")
    print(f"AES-ON dane: {sorted(data_on.keys())}")
    print(f"AES-OFF dane: {sorted(data_off.keys())}")
    print("Payload: 10MB, Concurrency: 32")

    print("\n📊 Dane na wykresie (AES-OFF impact on throughput):")
    print("Format: Port | AES-ON[MB/s] | AES-OFF[MB/s] | Delta[%]")

    ports = sorted(set(data_on.keys()) & set(data_off.keys()))
    for port in ports:
        thr_on = data_on[port]["throughput_mb_s"]
        thr_off = data_off[port]["throughput_mb_s"]
        delta_pct = ((thr_off / thr_on) - 1) * 100
        print(f"Port {port}: {thr_on:.1f} | {thr_off:.1f} | {delta_pct:+.1f}%")

    ports = sorted(set(data_on.keys()) & set(data_off.keys()))
    deltas = []

    for port in ports:
        thr_on = data_on[port]["throughput_mb_s"]
        thr_off = data_off[port]["throughput_mb_s"]
        delta_pct = ((thr_off / thr_on) - 1) * 100
        deltas.append(delta_pct)

    fig, ax = plt.subplots(figsize=(10, 6))

    x = range(len(ports))
    bars = ax.bar(x, deltas, color=COLORS["delta"], alpha=0.8)

    # Dodaj wartości na słupkach
    for i, delta in enumerate(deltas):
        ax.text(
            i,
            delta + 1 if delta >= 0 else delta - 1,
            f"{delta:+.1f}%",
            ha="center",
            va="bottom" if delta >= 0 else "top",
            fontweight="bold",
        )

    ax.set_xlabel("Port (OpenSSL only)")
    ax.set_ylabel("Change [%]")
    ax.set_title(
        "Fig.07 — Throughput AES-OFF Delta (10 MB, c=32)",
        fontsize=14,
        fontweight="bold",
    )
    ax.set_xticks(x)
    ax.set_xticklabels([PORT_NAMES[p] for p in ports])
    ax.axhline(y=0, color="black", linestyle="-", alpha=0.3)
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(
        output_dir / "fig07_throughput_aes_off_delta.png", dpi=300, bbox_inches="tight"
    )
    plt.close()
    print("✅ Fig.07 wygenerowany")


def fig08_0rtt_acceptance_rate(base_path: Path, output_dir: Path):
    """Fig.08 — 0-RTT acceptance rate (baseline)"""
    print("\n🔍 Fig.08 - Analiza danych 0-RTT Acceptance Rate:")
    print("Typ wykresu: Słupkowy (bar chart) z dwoma seriami")

    # Próbujemy załadować rzeczywiste dane 0-RTT
    early_data_sizes = [0.1, 1]
    ports = [4431, 4432, 8443]  # Tylko OpenSSL porty wspierają 0-RTT

    print(f"Porty do analizy: {ports}")
    print(f"Rozmiary early data: {early_data_sizes} MB")

    # Sprawdzamy czy mamy dane o akceptacji 0-RTT
    data_01 = load_0rtt_data(base_path, 0.1, ports)
    data_1 = load_0rtt_data(base_path, 1, ports)

    print(f"Dane 0-RTT (0.1 MB): {data_01}")
    print(f"Dane 0-RTT (1 MB): {data_1}")

    fig, ax = plt.subplots(figsize=(10, 6))

    x = np.arange(len(ports))
    width = 0.35

    # Używamy rzeczywistych czasów z danych (w ms)
    times_01 = []
    times_1 = []

    for port in ports:
        time_01 = data_01.get(port, {}).get("avg_time_s", 0) * 1000  # s -> ms
        time_1 = data_1.get(port, {}).get("avg_time_s", 0) * 1000  # s -> ms
        times_01.append(time_01)
        times_1.append(time_1)

    print("\n📊 Dane na wykresie (0-RTT timing):")
    print("Format: Port | 0.1MB time[ms] | 1MB time[ms] | Delta[ms]")
    for i, port in enumerate(ports):
        delta = times_1[i] - times_01[i]
        print(f"Port {port}: {times_01[i]:.1f} | {times_1[i]:.1f} | +{delta:.1f}")

    bars1 = ax.bar(
        x - width / 2,
        times_01,
        width,
        label="0.1 MB Early Data",
        color=COLORS["aes_on"],
        alpha=0.7,
    )
    bars2 = ax.bar(
        x + width / 2,
        times_1,
        width,
        label="1 MB Early Data",
        color=COLORS["aes_off"],
        alpha=0.7,
    )

    # Dodaj wartości na słupkach
    for i, (t01, t1) in enumerate(zip(times_01, times_1)):
        if t01 > 0:
            ax.text(
                i - width / 2,
                t01 + 20,
                f"{t01:.0f}ms",
                ha="center",
                va="bottom",
                fontweight="bold",
            )
        if t1 > 0:
            ax.text(
                i + width / 2,
                t1 + 20,
                f"{t1:.0f}ms",
                ha="center",
                va="bottom",
                fontweight="bold",
            )

    ax.set_xlabel("Port")
    ax.set_ylabel("0-RTT Attempt Duration [ms]")
    ax.set_title(
        "Fig.08 — 0-RTT Attempt Duration (acceptance=0%)",
        fontsize=14,
        fontweight="bold",
    )
    ax.set_xticks(x)
    ax.set_xticklabels([PORT_NAMES[p] for p in ports])
    ax.legend()
    ax.grid(True, alpha=0.3)

    # Dodaj informacyjną notatkę
    ax.text(
        0.5,
        0.9,
        "Serwer nie zaakceptował early-data w tym setupie.\n"
        + "Czasy pokazują próby 0-RTT (acceptance=0%)",
        transform=ax.transAxes,
        ha="center",
        va="center",
        bbox=dict(boxstyle="round,pad=0.5", facecolor="lightblue", alpha=0.7),
        fontsize=9,
    )

    print(
        "💡 Interpretacja: Wykres pokazuje czasy 0-RTT attempts (nie acceptance rate)"
    )
    print("   - Większe early data = dłuższy czas transferu")
    print("   - Brak informacji o akceptacji przez serwer")

    plt.tight_layout()
    plt.savefig(
        output_dir / "fig08_0rtt_performance_timing.png", dpi=300, bbox_inches="tight"
    )
    plt.close()
    print("✅ Fig.08 wygenerowany (naprawiona wersja)")


def fig09_0rtt_vs_full_post(base_path: Path, output_dir: Path):
    """Fig.09 — 0-RTT vs Full POST: TTFB/całkowity czas (baseline)"""
    print("\n🔍 Fig.09 - Analiza danych 0-RTT vs Full POST:")
    print("Typ wykresu: Słupkowy (bar chart) - porównanie czasów")

    data_0rtt = load_0rtt_data(base_path, 1, [4431, 4432, 8443])
    data_full_post = load_full_post_data(
        base_path, 8, [4431, 4432, 8443]
    )  # 8MB payload

    print(f"Dane 0-RTT: {data_0rtt}")
    print(f"Dane Full POST: {data_full_post}")

    print("\n📊 Dane na wykresie (timing comparison):")
    print("Format: Port | 0-RTT[ms] | Full POST[ms] | Delta[ms]")
    for port in [4431, 4432, 8443]:
        ortt_time = data_0rtt.get(port, {}).get("avg_time_s", 0) * 1000
        full_post_time = data_full_post.get(port, {}).get("avg_time_s", 0) * 1000
        delta = ortt_time - full_post_time if full_post_time > 0 else 0
        print(f"Port {port}: {ortt_time:.0f} | {full_post_time:.0f} | {delta:+.0f}")

    # Użyj rzeczywistych danych Full POST
    ports = [4431, 4432, 8443]

    fig, ax = plt.subplots(figsize=(10, 6))

    x = np.arange(len(ports))
    width = 0.35

    # 0-RTT times (w sekundach, konwertujemy na ms)
    ortt_times = []
    full_post_times = []

    for port in ports:
        ortt_time = data_0rtt.get(port, {}).get("avg_time_s", 0) * 1000
        full_post_time = data_full_post.get(port, {}).get("avg_time_s", 0) * 1000
        ortt_times.append(ortt_time)
        full_post_times.append(full_post_time)

    bars1 = ax.bar(
        x - width / 2,
        ortt_times,
        width,
        label="0-RTT Attempt (1MB)",
        color=COLORS["aes_on"],
        alpha=0.7,
    )
    bars2 = ax.bar(
        x + width / 2,
        full_post_times,
        width,
        label="Full POST (8MB)",
        color=COLORS["aes_off"],
        alpha=0.7,
    )

    # Dodaj wartości na słupkach
    for i, (time_0rtt, time_full_post) in enumerate(zip(ortt_times, full_post_times)):
        if time_0rtt > 0:
            ax.text(
                i - width / 2,
                time_0rtt + 20,
                f"{time_0rtt:.0f}ms",
                ha="center",
                va="bottom",
                fontweight="bold",
            )
        if time_full_post > 0:
            ax.text(
                i + width / 2,
                time_full_post + 20,
                f"{time_full_post:.0f}ms",
                ha="center",
                va="bottom",
                fontweight="bold",
            )

    ax.set_xlabel("Port")
    ax.set_ylabel("Total Time [ms]")
    ax.set_title(
        "Fig.09 — 0-RTT vs Full POST: Total Time (Baseline)",
        fontsize=14,
        fontweight="bold",
    )
    ax.set_xticks(x)
    ax.set_xticklabels([PORT_NAMES[p] for p in ports])
    ax.legend()
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(
        output_dir / "fig09_0rtt_vs_full_post.png", dpi=300, bbox_inches="tight"
    )
    plt.close()
    print("✅ Fig.09 wygenerowany")


def fig10_bytes_on_wire(base_path: Path, output_dir: Path):
    """Fig.10 — Bytes-on-the-wire per port (baseline)"""
    print("\n🔍 Fig.10 - Analiza danych Bytes-on-Wire:")
    print("Typ wykresu: Słupkowy (stacked bar) - rozmiar handshake")

    data = load_bytes_on_wire_data(base_path)

    if not data:
        print("❌ Brak danych dla Fig.10")
        return

    print(f"Porty z danymi: {sorted(data.keys())}")
    print("\n📊 Dane na wykresie (network overhead):")
    print("Format: Port | ClientHello[B] | Server[B] | Total[B] | Records")
    for port in sorted(data.keys()):
        d = data[port]
        print(
            f"Port {port}: {d['clienthello_bytes']} | {d['server_flight_bytes']} | {d['total_handshake_bytes']} | {d['total_records']}"
        )

    ports = sorted(data.keys())

    fig, ax = plt.subplots(figsize=(10, 6))

    x = range(len(ports))
    clienthello = [data[p]["clienthello_bytes"] for p in ports]
    server_flight = [data[p]["server_flight_bytes"] for p in ports]

    bars1 = ax.bar(
        x, clienthello, label="ClientHello", color=COLORS["aes_on"], alpha=0.7
    )
    bars2 = ax.bar(
        x,
        server_flight,
        bottom=clienthello,
        label="Server Flight",
        color=COLORS["aes_off"],
        alpha=0.7,
    )

    # Dodaj całkowite wartości na górze z Records
    for i, port in enumerate(ports):
        total = data[port]["total_handshake_bytes"]
        records = data[port]["total_records"]
        total_kb = total / 1024
        ax.text(
            i,
            total + 50,
            f"{total_kb:.1f}KB\n({records} rec)",
            ha="center",
            va="bottom",
            fontweight="bold",
            fontsize=9,
        )

    ax.set_xlabel("Port")
    ax.set_ylabel("Bytes [KB]")
    ax.set_title(
        "Fig.10 — Bytes-on-the-Wire per Port (Handshake)",
        fontsize=14,
        fontweight="bold",
    )
    ax.set_xticks(x)
    ax.set_xticklabels([PORT_NAMES[p] for p in ports])
    ax.legend()
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(output_dir / "fig10_bytes_on_wire.png", dpi=300, bbox_inches="tight")
    plt.close()
    print("✅ Fig.10 wygenerowany")


def fig11_openssl_speed_vs_throughput(base_path: Path, output_dir: Path):
    """Fig.11 — OpenSSL Speed vs Real Throughput (SCATTER PLOT)"""
    print("\n🔍 Fig.11 - Analiza danych OpenSSL Speed vs Throughput:")
    print("Typ wykresu: Scatter plot - korelacja micro vs macro benchmark")

    # OpenSSL speed (tylko jeden wynik dla wszystkich)
    speed_aes_on = parse_openssl_speed(base_path / "series/openssl_speed_aes_on.txt")

    # Real throughput dla OpenSSL portów
    data = load_throughput_data(base_path, "on", 10, 32, OPENSSL_PORTS)

    print(f"OpenSSL Speed (AES-128-GCM): {speed_aes_on:.1f} MB/s")
    print(f"Real throughput dane: {len(data)} portów")

    if not data or speed_aes_on == 0:
        print("❌ Brak danych dla Fig.11")
        return

    print("\n📊 Dane na wykresie (correlation):")
    print("Format: Port | OpenSSL Speed[MB/s] | HTTP Throughput[MB/s]")
    for port in OPENSSL_PORTS:
        if port in data:
            thr = data[port]["throughput_mb_s"]
            print(f"Port {port}: {speed_aes_on:.1f} | {thr:.1f}")

    fig, ax = plt.subplots(figsize=(10, 6))

    # Zmieniono na bar chart - porównanie OpenSSL speed vs rzeczywistego throughput
    throughputs = []
    port_labels = []

    for port in OPENSSL_PORTS:
        if port in data:
            throughputs.append(data[port]["throughput_mb_s"])
            port_labels.append(f"Port {port}")

    x = np.arange(len(port_labels))
    width = 0.35

    # OpenSSL speed jako referencja (linia pozioma)
    bars = ax.bar(
        x, throughputs, color=COLORS["aes_on"], alpha=0.7, label="HTTP Throughput"
    )

    # Dodaj OpenSSL speed jako linię referencyjną
    ax.axhline(
        y=speed_aes_on,
        color="red",
        linestyle="--",
        alpha=0.7,
        label=f"OpenSSL Speed: {speed_aes_on:.0f} MB/s",
    )

    # Dodaj wartości na słupkach
    for i, thr in enumerate(throughputs):
        ax.text(i, thr + 100, f"{thr:.1f}", ha="center", va="bottom", fontweight="bold")

    ax.set_xlabel("Port")
    ax.set_ylabel("Throughput [MB/s]")
    ax.set_title(
        "Fig.11 — OpenSSL Speed vs HTTP Throughput Comparison",
        fontsize=14,
        fontweight="bold",
    )
    ax.set_xticks(x)
    ax.set_xticklabels(port_labels)
    ax.legend()
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(
        output_dir / "fig11_openssl_speed_vs_throughput.png",
        dpi=300,
        bbox_inches="tight",
    )
    plt.close()
    print("✅ Fig.11 wygenerowany")


def fig12_dashboard_summary(base_path: Path, output_dir: Path):
    """Fig.12 — Dashboard 2×2 (syntetyczny „executive summary")"""
    fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(16, 12))

    # Panel 1: Handshake p50 (AES-ON)
    data_hs = load_handshake_data(base_path, "on", [4431, 4432, 8443, 4434, 4435])
    if data_hs:
        ports = sorted(data_hs.keys())
        p50_values = [data_hs[p]["p50"] for p in ports]
        x = range(len(ports))
        ax1.bar(x, p50_values, color=COLORS["aes_on"], alpha=0.7)
        ax1.set_title("Handshake p50 (AES-ON)", fontweight="bold")
        ax1.set_ylabel("Time [ms]")
        ax1.set_xticks(x)
        ax1.set_xticklabels([str(p) for p in ports])
        ax1.grid(True, alpha=0.3)

    # Panel 2: TTFB p50
    data_ttfb = load_ttfb_data(base_path, HTTP_PORTS)
    if data_ttfb:
        ports = sorted(data_ttfb.keys())
        ttfb_values = [data_ttfb[p]["ttfb_ms"] for p in ports]
        x = range(len(ports))
        ax2.bar(x, ttfb_values, color=COLORS["aes_on"], alpha=0.7)
        ax2.set_title("TTFB per Port", fontweight="bold")
        ax2.set_ylabel("TTFB [ms]")
        ax2.set_xticks(x)
        ax2.set_xticklabels([str(p) for p in ports])
        ax2.grid(True, alpha=0.3)

    # Panel 3: Throughput 10MB @ c=32
    data_thr = load_throughput_data(base_path, "on", 10, 32, HTTP_PORTS)
    if data_thr:
        ports = sorted(data_thr.keys())
        thr_values = [data_thr[p]["throughput_mb_s"] for p in ports]
        x = range(len(ports))
        ax3.bar(x, thr_values, color=COLORS["aes_on"], alpha=0.7)
        ax3.set_title("Throughput 10MB @ c=32", fontweight="bold")
        ax3.set_ylabel("MB/s")
        ax3.set_xticks(x)
        ax3.set_xticklabels([str(p) for p in ports])
        ax3.grid(True, alpha=0.3)

    # Panel 4: Δ% AES-OFF (tylko OpenSSL)
    data_on = load_throughput_data(base_path, "on", 10, 32, OPENSSL_PORTS)
    data_off = load_throughput_data(base_path, "off", 10, 32, OPENSSL_PORTS)
    if data_on and data_off:
        ports = sorted(set(data_on.keys()) & set(data_off.keys()))
        deltas = []
        for port in ports:
            thr_on = data_on[port]["throughput_mb_s"]
            thr_off = data_off[port]["throughput_mb_s"]
            delta_pct = ((thr_off / thr_on) - 1) * 100
            deltas.append(delta_pct)

        x = range(len(ports))
        ax4.bar(x, deltas, color=COLORS["delta"], alpha=0.8)
        ax4.set_title("Δ% AES-OFF (OpenSSL)", fontweight="bold")
        ax4.set_ylabel("Change [%]")
        ax4.set_xticks(x)
        ax4.set_xticklabels([str(p) for p in ports])
        ax4.axhline(y=0, color="black", linestyle="-", alpha=0.3)
        ax4.grid(True, alpha=0.3)

    plt.suptitle("Fig.12 — Executive Summary Dashboard", fontsize=16, fontweight="bold")
    plt.tight_layout()
    plt.savefig(
        output_dir / "fig12_dashboard_summary.png", dpi=300, bbox_inches="tight"
    )
    plt.close()
    print("✅ Fig.12 wygenerowany")


def get_cert_size_der(cert_path: Path) -> int:
    """Oblicza rozmiar certyfikatu w DER format"""
    try:
        import subprocess

        result = subprocess.run(
            ["openssl", "x509", "-in", str(cert_path), "-outform", "DER"],
            capture_output=True,
        )
        return len(result.stdout) if result.returncode == 0 else 0
    except Exception as e:
        print(f"Błąd obliczania rozmiaru certyfikatu {cert_path}: {e}")
        return 0


def fig13_cert_chain_vs_handshake(base_path: Path, output_dir: Path):
    """Fig.13 — Handshake Latency by Implementation (ZMIENIONY)"""
    print("\n🔍 Fig.13 - Analiza danych Handshake by Implementation:")
    print("Typ wykresu: Słupkowy (bar chart) - latencja per implementacja")

    # Mapowanie portów do certyfikatów (na podstawie konfiguracji)
    cert_mapping = {
        4431: "ecdsa-p256.crt",  # nginx OpenSSL AES-GCM
        4432: "ecdsa-p256.crt",  # nginx OpenSSL ChaCha20
        8443: "ecdsa-p256.crt",  # nginx OpenSSL Hybrid
        4434: "ecdsa-p256.crt",  # lighttpd wolfSSL AES-GCM
        4435: "ecdsa-p256.crt",  # lighttpd wolfSSL ChaCha20
        11112: "ecdsa-p256.crt",  # wolfSSL PQ
    }

    print(f"Certyfikaty: wszędzie {list(set(cert_mapping.values()))}")

    # Ładowanie danych handshake
    data_hs = load_handshake_data(base_path, "on", list(cert_mapping.keys()))

    if not data_hs:
        print("❌ Brak danych dla Fig.13")
        return

    # Sprawdź rozmiar certyfikatu
    certs_path = Path("certs")
    cert_file = certs_path / "ecdsa-p256.crt"
    cert_size = get_cert_size_der(cert_file)

    print(f"Rozmiar certyfikatu ECDSA: {cert_size} bytes DER")
    print("\n📊 Dane na wykresie (cert size vs handshake):")
    print("Format: Port | Cert Size[B] | Handshake p50[ms]")
    for port in sorted(data_hs.keys()):
        p50 = data_hs[port]["p50"]
        print(f"Port {port}: {cert_size} | {p50:.1f}")

    print("💡 Zmieniono na porównanie implementacji (OpenSSL vs wolfSSL)")

    fig, ax = plt.subplots(figsize=(10, 6))

    # Grupowanie po implementacji
    openssl_ports = [p for p in [4431, 4432, 8443] if p in data_hs]
    wolfssl_ports = [p for p in [4434, 4435, 11112] if p in data_hs]

    openssl_latencies = [data_hs[p]["p50"] for p in openssl_ports]
    wolfssl_latencies = [data_hs[p]["p50"] for p in wolfssl_ports]

    openssl_labels = [PORT_NAMES[p] for p in openssl_ports]
    wolfssl_labels = [PORT_NAMES[p] for p in wolfssl_ports]

    x_openssl = np.arange(len(openssl_ports))
    x_wolfssl = np.arange(len(wolfssl_ports)) + len(openssl_ports) + 0.5

    bars1 = ax.bar(
        x_openssl, openssl_latencies, color=COLORS["aes_on"], alpha=0.7, label="OpenSSL"
    )
    bars2 = ax.bar(
        x_wolfssl,
        wolfssl_latencies,
        color=COLORS["aes_off"],
        alpha=0.7,
        label="wolfSSL",
    )

    # Dodaj wartości na słupkach
    for i, lat in enumerate(openssl_latencies):
        ax.text(i, lat + 2, f"{lat:.0f}ms", ha="center", va="bottom", fontweight="bold")

    for i, lat in enumerate(wolfssl_latencies):
        ax.text(
            i + len(openssl_ports) + 0.5,
            lat + 2,
            f"{lat:.0f}ms",
            ha="center",
            va="bottom",
            fontweight="bold",
        )

    ax.set_xlabel("Implementation & Port")
    ax.set_ylabel("Handshake Latency [ms]")
    ax.set_title(
        "Fig.13 — Handshake Latency by Implementation",
        fontsize=14,
        fontweight="bold",
    )

    # Ustaw etykiety osi X
    all_ticks = list(x_openssl) + list(x_wolfssl)
    all_labels = openssl_labels + wolfssl_labels
    ax.set_xticks(all_ticks)
    ax.set_xticklabels(all_labels, rotation=45, ha="right")

    ax.legend()
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(
        output_dir / "fig13_cert_chain_vs_handshake.png", dpi=300, bbox_inches="tight"
    )
    plt.close()
    print("✅ Fig.13 wygenerowany")


def fig14_concurrency_scaling_ratio(base_path: Path, output_dir: Path):
    """Fig.14 — Concurrency scaling ratio (32/8)"""
    print("\n🔍 Fig.14 - Analiza danych Concurrency Scaling:")
    print("Typ wykresu: Słupkowy (bar chart) - scaling ratio per payload")

    payloads = [1, 10]

    print(f"Payloads: {payloads} MB")
    print("Scaling ratio = Throughput(c=32) / Throughput(c=8)")

    fig, ax = plt.subplots(figsize=(12, 6))

    x = np.arange(len(HTTP_PORTS))
    width = 0.35

    ratios_1mb = []
    ratios_10mb = []

    for payload in payloads:
        data_c8 = load_throughput_data(base_path, "on", payload, 8, HTTP_PORTS)
        data_c32 = load_throughput_data(base_path, "on", payload, 32, HTTP_PORTS)

        print(f"\nPayload {payload}MB:")
        print(f"  c=8: {len(data_c8)} portów")
        print(f"  c=32: {len(data_c32)} portów")

        ratios = []
        for port in HTTP_PORTS:
            if port in data_c8 and port in data_c32:
                thr_c8 = data_c8[port]["throughput_mb_s"]
                thr_c32 = data_c32[port]["throughput_mb_s"]
                ratio = thr_c32 / thr_c8 if thr_c8 > 0 else 0
                ratios.append(ratio)
                print(f"  Port {port}: {thr_c8:.1f} -> {thr_c32:.1f} = {ratio:.2f}x")
            else:
                ratios.append(0)
                print(f"  Port {port}: brak danych")

        if payload == 1:
            ratios_1mb = ratios
        else:
            ratios_10mb = ratios

    print("\n📊 Dane na wykresie (scaling ratios):")
    print("Format: Port | 1MB ratio | 10MB ratio")
    for i, port in enumerate(HTTP_PORTS):
        print(f"Port {port}: {ratios_1mb[i]:.2f}x | {ratios_10mb[i]:.2f}x")

    bars1 = ax.bar(
        x - width / 2,
        ratios_1mb,
        width,
        label="1 MB",
        color=COLORS["aes_on"],
        alpha=0.7,
    )
    bars2 = ax.bar(
        x + width / 2,
        ratios_10mb,
        width,
        label="10 MB",
        color=COLORS["aes_off"],
        alpha=0.7,
    )

    # Dodaj wartości na słupkach
    for i, (r1, r10) in enumerate(zip(ratios_1mb, ratios_10mb)):
        if r1 > 0:
            ax.text(
                i - width / 2,
                r1 + 0.05,
                f"{r1:.2f}x",
                ha="center",
                va="bottom",
                fontsize=9,
                fontweight="bold",
            )
        if r10 > 0:
            ax.text(
                i + width / 2,
                r10 + 0.05,
                f"{r10:.2f}x",
                ha="center",
                va="bottom",
                fontsize=9,
                fontweight="bold",
            )

    # Dodaj linię 1:1 (idealnej skalowalności liniowej = 4x)
    ax.axhline(
        y=4.0, color="red", linestyle="--", alpha=0.7, label="Linear scaling (4x)"
    )

    ax.set_xlabel("Port")
    ax.set_ylabel("Scaling Ratio (Throughput c=32 / c=8)")
    ax.set_title(
        "Fig.14 — Concurrency Scaling Ratio (32/8)", fontsize=14, fontweight="bold"
    )
    ax.set_xticks(x)
    ax.set_xticklabels([PORT_NAMES[p] for p in HTTP_PORTS])
    ax.legend()
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(
        output_dir / "fig14_concurrency_scaling_ratio.png", dpi=300, bbox_inches="tight"
    )
    plt.close()
    print("✅ Fig.14 wygenerowany")


def fig15_throughput_distribution(base_path: Path, output_dir: Path):
    """Fig.15 — Rozkład throughput (1 MB vs 10 MB)"""
    print("\n🔍 Fig.15 - Analiza danych Throughput Distribution:")
    print(
        "Typ wykresu: Grouped bar chart - porównanie przepustowości (zamiast boxplot)"
    )

    # Ładowanie danych dla obu rozmiarów payload
    data_1mb = load_throughput_data(base_path, "on", 1, 32, HTTP_PORTS)
    data_10mb = load_throughput_data(base_path, "on", 10, 32, HTTP_PORTS)

    print(f"Dane 1MB: {len(data_1mb)} portów")
    print(f"Dane 10MB: {len(data_10mb)} portów")

    if not data_1mb or not data_10mb:
        print("❌ Brak danych dla Fig.15")
        return

    print("\n📊 Dane na wykresie (throughput values):")
    print("Format: Port | 1MB[MB/s] | 10MB[MB/s] | Note")
    for port in sorted(set(data_1mb.keys()) | set(data_10mb.keys())):
        thr_1mb = data_1mb.get(port, {}).get("throughput_mb_s", 0)
        thr_10mb = data_10mb.get(port, {}).get("throughput_mb_s", 0)
        note = (
            "Single measurement per port"
            if thr_1mb > 0 and thr_10mb > 0
            else "Missing data"
        )
        print(f"Port {port}: {thr_1mb:.1f} | {thr_10mb:.1f} | {note}")

    print("💡 Grouped bar chart zamiast box plots (pojedyncze pomiary per port)")

    fig, ax = plt.subplots(figsize=(12, 8))

    # Przygotuj dane dla grouped bar chart
    ports = sorted(set(data_1mb.keys()) | set(data_10mb.keys()))
    port_labels = [PORT_NAMES[p] for p in ports]

    throughputs_1mb = []
    throughputs_10mb = []

    for port in ports:
        thr_1mb = data_1mb.get(port, {}).get("throughput_mb_s", 0)
        thr_10mb = data_10mb.get(port, {}).get("throughput_mb_s", 0)
        throughputs_1mb.append(thr_1mb)
        throughputs_10mb.append(thr_10mb)

    x = np.arange(len(ports))
    width = 0.35

    bars1 = ax.bar(
        x - width / 2,
        throughputs_1mb,
        width,
        label="1 MB Payload",
        color=COLORS["aes_on"],
        alpha=0.7,
    )
    bars2 = ax.bar(
        x + width / 2,
        throughputs_10mb,
        width,
        label="10 MB Payload",
        color=COLORS["aes_off"],
        alpha=0.7,
    )

    # Dodaj wartości na słupkach
    for i, (thr1, thr10) in enumerate(zip(throughputs_1mb, throughputs_10mb)):
        if thr1 > 0:
            ax.text(
                i - width / 2,
                thr1 + 5,
                f"{thr1:.1f}",
                ha="center",
                va="bottom",
                fontweight="bold",
            )
        if thr10 > 0:
            ax.text(
                i + width / 2,
                thr10 + 5,
                f"{thr10:.1f}",
                ha="center",
                va="bottom",
                fontweight="bold",
            )

    ax.set_xlabel("Port")
    ax.set_ylabel("Throughput [MB/s]")
    ax.set_title(
        "Fig.15 — Throughput Distribution (1 MB vs 10 MB)",
        fontsize=14,
        fontweight="bold",
    )
    ax.set_xticks(x)
    ax.set_xticklabels(port_labels, rotation=45, ha="right")
    ax.legend()
    ax.grid(True, alpha=0.3)

    # Dodaj notatkę o pojedynczych pomiarach
    fig.text(
        0.5,
        0.02,
        "Note: Single measurement per port (box shows p50 marker)",
        ha="center",
        va="bottom",
        bbox=dict(boxstyle="round,pad=0.3", facecolor="yellow", alpha=0.7),
    )

    plt.tight_layout()
    plt.savefig(
        output_dir / "fig15_throughput_distribution.png", dpi=300, bbox_inches="tight"
    )
    plt.close()
    print("✅ Fig.15 wygenerowany")


def main():
    """Główna funkcja generująca wszystkie wykresy Z LOGOWANIEM"""
    base_path = Path("results")
    output_dir = Path("figures")
    output_dir.mkdir(exist_ok=True)

    print("🚀 Generowanie wykresów TLS Performance & Security Analysis")
    print("🔍 TRYB DEBUG: Wyświetlanie danych dla każdego wykresu")
    print("=" * 60)

    # Generuj wszystkie wykresy (1-15) z logowaniem
    fig01_handshake_latency_aes_on(base_path, output_dir)
    fig02_handshake_aes_off_delta(base_path, output_dir)
    fig03_cdf_handshake_aes_on(base_path, output_dir)
    fig04_ttfb_per_port(base_path, output_dir)
    fig05_throughput_vs_concurrency(base_path, output_dir)
    fig06_throughput_payload_size(base_path, output_dir)
    fig07_throughput_aes_off_delta(base_path, output_dir)
    fig08_0rtt_acceptance_rate(base_path, output_dir)
    fig09_0rtt_vs_full_post(base_path, output_dir)
    fig10_bytes_on_wire(base_path, output_dir)
    fig11_openssl_speed_vs_throughput(base_path, output_dir)
    fig12_dashboard_summary(base_path, output_dir)

    # Dodatkowe wykresy (13-15)
    fig13_cert_chain_vs_handshake(base_path, output_dir)
    fig14_concurrency_scaling_ratio(base_path, output_dir)
    fig15_throughput_distribution(base_path, output_dir)

    print("=" * 60)
    print(f"✅ Wszystkie wykresy wygenerowane w katalogu: {output_dir}")
    print("📊 Lista wygenerowanych plików:")
    for png_file in sorted(output_dir.glob("*.png")):
        print(f"   - {png_file.name}")


if __name__ == "__main__":
    main()
