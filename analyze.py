# analyze.py
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
        "-s", "--separate", action="store_true", help="generuj każdy wykres osobno"
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


def load_data(run_dir):
    csv = run_dir / "bench.csv"
    if not csv.exists():
        print(f"❌ Brak {csv}")
        sys.exit(1)
    df = read_csv_robust(csv)
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


def prepare_data(df):
    m = {
        "mean_ms": "handshake_ms",
        "rps": "throughput_rps",
        "mean_time_s": "response_time_s",
        "throughput_mb_s": "throughput_mb_s",
    }
    df["metric_clean"] = df.metric.map(m).fillna(df.metric)
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
    df2 = df[df.metric_clean.isin(keep)]
    p = df2.pivot_table(
        index=["implementation", "suite", "test", "run"],
        columns="metric_clean",
        values="value",
        aggfunc="first",
    ).reset_index()
    if "throughput_rps" in p:
        p["throughput_mb_s"] = p["throughput_rps"] * 1.0
    sm = {
        "x25519_aesgcm": "Traditional (X25519+AES-GCM)",
        "chacha20": "Traditional (X25519+ChaCha20)",
        "kyber_hybrid": "Post-Quantum (X25519+ML-KEM768)",
    }
    p["algorithm"] = p.suite.map(sm).fillna(p.suite)
    p["quantum_resistant"] = p.suite.apply(
        lambda x: "Post-Quantum" if "kyber" in x else "Traditional"
    )
    return p


def create_visualizations(df, run_dir, separate):
    run_name = run_dir.name
    figs = Path("figures") / run_name / "analyze"
    figs.mkdir(exist_ok=True, parents=True)
    sns.set_palette("husl")

    # overview 4-in-1
    fig, axes = plt.subplots(2, 2, figsize=(16, 12))
    fig.suptitle("TLS Performance Analysis: Post-Quantum vs Traditional", fontsize=16)
    if "handshake_ms" in df:
        sns.boxplot(df, x="algorithm", y="handshake_ms", ax=axes[0, 0])
        axes[0, 0].set_title("Handshake Latency (ms)")
        axes[0, 0].tick_params(axis="x", rotation=45)
    tcol = next((c for c in ["throughput_mb_s", "throughput_rps"] if c in df), None)
    if tcol:
        sns.boxplot(df, x="algorithm", y=tcol, ax=axes[0, 1])
        axes[0, 1].set_title("Throughput")
        axes[0, 1].tick_params(axis="x", rotation=45)
    if "handshake_ms" in df:
        sns.barplot(
            df,
            x="implementation",
            y="handshake_ms",
            hue="quantum_resistant",
            ax=axes[1, 0],
        )
        axes[1, 0].set_title("Handshake by Implementation")
        axes[1, 0].tick_params(axis="x", rotation=45)
    if "response_time_s" in df:
        sns.violinplot(df, x="quantum_resistant", y="response_time_s", ax=axes[1, 1])
        axes[1, 1].set_title("Response Time (s)")
    plt.tight_layout()
    plt.savefig(figs / "tls_overview.png", dpi=300)
    plt.close()

    if separate:
        # handshake_latency
        plt.figure(figsize=(8, 5))
        sns.boxplot(df, x="algorithm", y="handshake_ms")
        plt.title("Handshake Latency (ms)")
        plt.xticks(rotation=45)
        plt.tight_layout()
        plt.savefig(figs / "handshake_latency.png", dpi=300)
        plt.close()
        # throughput
        plt.figure(figsize=(8, 5))
        sns.boxplot(df, x="algorithm", y=tcol)
        plt.title("Throughput")
        plt.xticks(rotation=45)
        plt.tight_layout()
        plt.savefig(figs / "throughput.png", dpi=300)
        plt.close()
        # impl_handshake
        plt.figure(figsize=(8, 5))
        sns.barplot(df, x="implementation", y="handshake_ms", hue="quantum_resistant")
        plt.title("Handshake by Implementation")
        plt.xticks(rotation=45)
        plt.tight_layout()
        plt.savefig(figs / "impl_handshake.png", dpi=300)
        plt.close()
        # response_dist
        plt.figure(figsize=(8, 5))
        sns.violinplot(df, x="quantum_resistant", y="response_time_s")
        plt.title("Response Time Distribution")
        plt.tight_layout()
        plt.savefig(figs / "response_dist.png", dpi=300)
        plt.close()

    # post-quantum impact
    if "quantum_resistant" in df:
        metrics = [
            m for m in ["handshake_ms", "throughput_rps", "response_time_s"] if m in df
        ]
        fig2, axs2 = plt.subplots(1, len(metrics), figsize=(6 * len(metrics), 6))
        if len(metrics) == 1:
            axs2 = [axs2]
        for ax, m in zip(axs2, metrics):
            sns.boxplot(df, x="quantum_resistant", y=m, ax=ax)
            trad = df[df.quantum_resistant == "Traditional"][m]
            pq = df[df.quantum_resistant == "Post-Quantum"][m]
            if not trad.empty and not pq.empty:
                imp = (pq.mean() - trad.mean()) / trad.mean() * 100
                ax.set_title(f"{m}: {imp:+.1f}%")
            else:
                ax.set_title(m)
        plt.tight_layout()
        plt.savefig(figs / "post_quantum_impact.png", dpi=300)
        plt.close()

    # implementation comparison
    impls = df.implementation.unique()
    if len(impls) > 1:
        fig3, axs3 = plt.subplots(1, 2, figsize=(14, 6))
        fig3.suptitle("Implementation Comparison")
        if "handshake_ms" in df:
            sns.barplot(
                df, x="implementation", y="handshake_ms", hue="suite", ax=axs3[0]
            )
            axs3[0].set_title("Handshake Latency")
            axs3[0].tick_params(axis="x", rotation=45)
        if tcol:
            sns.barplot(df, x="implementation", y=tcol, hue="suite", ax=axs3[1])
            axs3[1].set_title("Throughput")
            axs3[1].tick_params(axis="x", rotation=45)
        plt.tight_layout()
        plt.savefig(figs / "impl_comparison.png", dpi=300)
        plt.close()


def main():
    args = parse_args()
    run_dir = Path(args.run)
    df_raw, netem = load_data(run_dir)
    df = prepare_data(df_raw)
    create_visualizations(df, run_dir, args.separate)
    print(f"✓ Wykresy zapisane w: figures/{run_dir.name}/analyze")


if __name__ == "__main__":
    main()
