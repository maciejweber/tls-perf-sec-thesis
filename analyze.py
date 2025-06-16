#!/usr/bin/env python3
import argparse
import sys
import re
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path


def parse_args():
    p = argparse.ArgumentParser(description="Analiza TLS performance")
    p.add_argument(
        "-r",
        "--run",
        default="results/latest",
        help="katalog run_... (domyślnie results/latest)",
    )
    p.add_argument(
        "-s",
        "--separate",
        action="store_true",
        help="generuj każdy wykres osobno",
    )
    return p.parse_args()


def read_csv_robust(path):
    try:
        return pd.read_csv(path)
    except pd.errors.ParserError:
        rows = []
        with open(path) as f:
            hdr = f.readline().strip().split(",")
            for line in f:
                line = line.strip()
                if not line:
                    continue
                if "[" in line:
                    parts, cur = [], ""
                    inarr = False
                    for ch in line:
                        if ch == "[":
                            inarr = True
                            cur += ch
                        elif ch == "]":
                            inarr = False
                            cur += ch
                        elif ch == "," and not inarr:
                            parts.append(cur)
                            cur = ""
                        else:
                            cur += ch
                    parts.append(cur)
                else:
                    parts = line.split(",")
                while len(parts) < len(hdr):
                    parts.append("")
                rows.append({hdr[i]: parts[i] for i in range(len(hdr))})
        df = pd.DataFrame(rows)
        for c in ["run", "value"]:
            if c in df:
                df[c] = pd.to_numeric(df[c], errors="coerce")
        return df


def load_data(run_dir: Path):
    csv = run_dir / "bench.csv"
    if not csv.exists():
        print(f"❌ Brak {csv}")
        sys.exit(1)
    df = read_csv_robust(csv)
    # parsowanie config.txt (opcjonalnie netem)
    cfg = {"delay": 0, "loss": 0.0}
    txt = run_dir / "config.txt"
    if txt.exists():
        t = txt.read_text()
        m1 = re.search(r"delay=(\d+)ms", t)
        m2 = re.search(r"loss=([\d.]+)", t)
        if m1:
            cfg["delay"] = int(m1.group(1))
        if m2:
            cfg["loss"] = float(m2.group(1))
    return df, cfg


def prepare_data(df: pd.DataFrame) -> pd.DataFrame:
    mapping = {
        "mean_ms": "handshake_ms",
        "rps": "throughput_rps",
        "mean_time_s": "response_time_s",
        "throughput_mb_s": "throughput_mb_s",
    }
    df["metric_clean"] = df.metric.map(mapping).fillna(df.metric)
    keep = [
        "handshake_ms",
        "throughput_rps",
        "response_time_s",
        "throughput_mb_s",
        "stddev_ms",
        "samples",
        "failed_measurements",
        "failed_requests",
    ]
    df = df[df.metric_clean.isin(keep)]
    pivot = df.pivot_table(
        index=["implementation", "suite", "test", "run"],
        columns="metric_clean",
        values="value",
        aggfunc="first",
    ).reset_index()
    # preferujemy throughput_rps
    if "throughput_rps" not in pivot.columns and "throughput_mb_s" in pivot.columns:
        pivot["throughput_rps"] = pivot["throughput_mb_s"]
    # czytelne nazwy algorytmów
    suite_map = {
        "x25519_aesgcm": "AES-GCM (AES-NI)",
        "chacha20": "ChaCha20",
        "kyber_hybrid": "Kyber-hybrydowy",
    }
    pivot["algorithm"] = pivot.suite.map(suite_map).fillna(pivot.suite)
    pivot["quantum_resistant"] = pivot.suite.apply(
        lambda s: "Post-Quantum" if "kyber" in s else "Traditional"
    )
    return pivot


def annotate_bars(ax, fmt="{:.0f}", offset=0.02):
    for p in ax.patches:
        h = p.get_height()
        if pd.notna(h):
            va = "bottom" if h >= 0 else "top"
            y = h + offset * max(abs(h), 1)
            ax.annotate(
                fmt.format(h),
                (p.get_x() + p.get_width() / 2, y),
                ha="center",
                va=va,
                fontsize=8,
            )


def create_visualizations(df: pd.DataFrame, run_dir: Path, separate: bool):
    run_name = run_dir.name
    figs = Path("figures") / run_name / "analyze"
    figs.mkdir(exist_ok=True, parents=True)
    sns.set_palette("husl")

    # === 1) TLS Overview (4-in-1) ===
    fig, axes = plt.subplots(2, 2, figsize=(16, 12))
    fig.suptitle("TLS Performance: Post-Quantum vs Traditional", fontsize=16)

    # 1a) Handshake latency by algorithm
    sns.boxplot(data=df, x="algorithm", y="handshake_ms", ax=axes[0, 0])
    axes[0, 0].set_title("Handshake Latency (ms)")
    axes[0, 0].tick_params(axis="x", rotation=45)

    # 1b) Throughput by algorithm
    sns.boxplot(data=df, x="algorithm", y="throughput_rps", ax=axes[0, 1])
    axes[0, 1].set_title("Throughput (RPS)")
    axes[0, 1].tick_params(axis="x", rotation=45)

    # 1c) Handshake by implementation
    ax1 = axes[1, 0]
    sns.barplot(
        data=df, x="implementation", y="handshake_ms", hue="quantum_resistant", ax=ax1
    )
    ax1.set_title("Handshake Latency by Implementation")
    ax1.tick_params(axis="x", rotation=45)
    annotate_bars(ax1, fmt="{:.0f}")

    # 1d) Response time distribution
    sns.violinplot(data=df, x="quantum_resistant", y="response_time_s", ax=axes[1, 1])
    axes[1, 1].set_title("Response Time (s)")

    plt.tight_layout()
    fig.savefig(figs / "tls_overview.png", dpi=300)
    plt.close(fig)

    # === 2) Separate plots ===
    if separate:
        # 2a) Handshake latency by implementation
        fig = plt.figure(figsize=(8, 5))
        ax = sns.barplot(data=df, x="implementation", y="handshake_ms", hue="suite")
        ax.set_title("Handshake Latency (ms) by Implementation")
        ax.tick_params(axis="x", rotation=45)
        annotate_bars(ax, fmt="{:.0f}")
        plt.tight_layout()
        fig.savefig(figs / "handshake_latency.png", dpi=300)
        plt.close(fig)

        # 2b) Throughput by implementation
        fig = plt.figure(figsize=(8, 5))
        ax = sns.barplot(data=df, x="implementation", y="throughput_rps", hue="suite")
        ax.set_title("Throughput (RPS) by Implementation")
        ax.tick_params(axis="x", rotation=45)
        annotate_bars(ax, fmt="{:.1f}")
        plt.tight_layout()
        fig.savefig(figs / "throughput.png", dpi=300)
        plt.close(fig)

        # 2c) Handshake latency by algorithm
        fig = plt.figure(figsize=(8, 5))
        ax = sns.boxplot(data=df, x="algorithm", y="handshake_ms")
        ax.set_title("Handshake Latency (ms) by Algorithm")
        ax.tick_params(axis="x", rotation=45)
        plt.tight_layout()
        fig.savefig(figs / "handshake_by_algo.png", dpi=300)
        plt.close(fig)

        # 2d) Throughput by algorithm
        fig = plt.figure(figsize=(8, 5))
        ax = sns.boxplot(data=df, x="algorithm", y="throughput_rps")
        ax.set_title("Throughput (RPS) by Algorithm")
        ax.tick_params(axis="x", rotation=45)
        plt.tight_layout()
        fig.savefig(figs / "throughput_by_algo.png", dpi=300)
        plt.close(fig)

        # 2e) Response time distribution
        fig = plt.figure(figsize=(8, 5))
        ax = sns.violinplot(data=df, x="quantum_resistant", y="response_time_s")
        ax.set_title("Response Time Distribution")
        plt.tight_layout()
        fig.savefig(figs / "response_dist.png", dpi=300)
        plt.close(fig)

    # === 3) Post-Quantum Impact ===
    metrics = ["handshake_ms", "throughput_rps", "response_time_s"]
    present = [m for m in metrics if m in df]
    if present:
        fig2, axs2 = plt.subplots(1, len(present), figsize=(6 * len(present), 6))
        if len(present) == 1:
            axs2 = [axs2]
        for ax, m in zip(axs2, present):
            sns.boxplot(data=df, x="quantum_resistant", y=m, ax=ax)
            trad = df[df.quantum_resistant == "Traditional"][m]
            pq = df[df.quantum_resistant == "Post-Quantum"][m]
            if not trad.empty and not pq.empty:
                imp = (pq.mean() - trad.mean()) / trad.mean() * 100
                ax.set_title(f"{m}: {imp:+.1f}%")
            else:
                ax.set_title(m)
        plt.tight_layout()
        fig2.savefig(figs / "post_quantum_impact.png", dpi=300)
        plt.close(fig2)

    # === 4) Implementation Comparison (2-in-1) ===
    if df.implementation.nunique() > 1:
        fig3, axs3 = plt.subplots(1, 2, figsize=(14, 6))
        fig3.suptitle("Implementation Comparison", fontsize=14)
        ax0 = axs3[0]
        sns.barplot(data=df, x="implementation", y="handshake_ms", hue="suite", ax=ax0)
        ax0.set_title("Handshake Latency")
        ax0.tick_params(axis="x", rotation=45)
        annotate_bars(ax0, fmt="{:.0f}")
        ax1 = axs3[1]
        sns.barplot(
            data=df, x="implementation", y="throughput_rps", hue="suite", ax=ax1
        )
        ax1.set_title("Throughput (RPS)")
        ax1.tick_params(axis="x", rotation=45)
        annotate_bars(ax1, fmt="{:.1f}")
        plt.tight_layout()
        fig3.savefig(figs / "impl_comparison.png", dpi=300)
        plt.close(fig3)


def main():
    args = parse_args()
    run_dir = Path(args.run)
    df_raw, netem = load_data(run_dir)
    df = prepare_data(df_raw)
    create_visualizations(df, run_dir, args.separate)
    print(f"✓ Wykresy zapisane w: figures/{run_dir.name}/analyze")


if __name__ == "__main__":
    main()
