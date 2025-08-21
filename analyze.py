#!/usr/bin/env python3
import argparse
import sys
import re
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np
import os
from pathlib import Path
from scipy.stats import spearmanr


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
        "ttfb_s": "ttfb_s",
        "avg_time_s": "avg_time_s",
    }
    # Warm-up trimming: drop first N runs per (implementation,suite,test)
    warmup_drop = int(os.environ.get("WARMUP_DROP", "3"))
    if warmup_drop > 0 and {"implementation", "suite", "test", "run"}.issubset(
        df.columns
    ):
        trimmed = []
        for (impl, suite, test), grp in df.groupby(
            ["implementation", "suite", "test"], sort=False
        ):
            g2 = grp.sort_values("run")
            g2 = g2[g2["run"] > (g2["run"].min() + warmup_drop - 1)]
            trimmed.append(g2)
        if trimmed:
            df = pd.concat(trimmed, ignore_index=True)
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
        "ttfb_s",
        "avg_time_s",
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

    # === 0) Optional: bytes-on-the-wire table snapshot ===
    bow_csv = Path("results") / "bytes_on_wire.csv"
    if bow_csv.exists():
        try:
            bow = pd.read_csv(bow_csv)
            bow.to_csv(figs / "bytes_on_wire_table.csv", index=False)
        except Exception:
            pass

    # === 1) TLS Overview (4-in-1) ===
    fig, axes = plt.subplots(2, 2, figsize=(16, 12))
    fig.suptitle("TLS Performance: Post-Quantum vs Traditional", fontsize=16)

    # 1a) Handshake latency by algorithm
    if "handshake_ms" in df:
        sns.boxplot(data=df, x="algorithm", y="handshake_ms", ax=axes[0, 0])
        axes[0, 0].set_title("Handshake Latency (ms)")
        axes[0, 0].tick_params(axis="x", rotation=45)

    # 1b) Throughput by algorithm
    if "throughput_rps" in df:
        sns.boxplot(data=df, x="algorithm", y="throughput_rps", ax=axes[0, 1])
        axes[0, 1].set_title("Throughput (RPS)")
        axes[0, 1].tick_params(axis="x", rotation=45)

    # 1c) Handshake by implementation
    if "handshake_ms" in df:
        ax1 = axes[1, 0]
        sns.barplot(
            data=df,
            x="implementation",
            y="handshake_ms",
            hue="quantum_resistant",
            ax=ax1,
        )
        ax1.set_title("Handshake Latency by Implementation")
        ax1.tick_params(axis="x", rotation=45)
        annotate_bars(ax1, fmt="{:.0f}")

    # 1d) Response time distribution
    if "response_time_s" in df:
        sns.violinplot(
            data=df, x="quantum_resistant", y="response_time_s", ax=axes[1, 1]
        )
        axes[1, 1].set_title("Response Time (s)")

    plt.tight_layout()
    fig.savefig(figs / "tls_overview.png", dpi=300)
    plt.close(fig)

    # === 2) Separate plots ===
    if separate:
        # 2a) Handshake latency by implementation
        if "handshake_ms" in df:
            fig = plt.figure(figsize=(8, 5))
            ax = sns.barplot(data=df, x="implementation", y="handshake_ms", hue="suite")
            ax.set_title("Handshake Latency (ms) by Implementation")
            ax.tick_params(axis="x", rotation=45)
            annotate_bars(ax, fmt="{:.0f}")
            plt.tight_layout()
            fig.savefig(figs / "handshake_latency.png", dpi=300)
            plt.close(fig)

        # 2b) Throughput by implementation
        if "throughput_rps" in df:
            fig = plt.figure(figsize=(8, 5))
            ax = sns.barplot(
                data=df, x="implementation", y="throughput_rps", hue="suite"
            )
            ax.set_title("Throughput (RPS) by Implementation")
            ax.tick_params(axis="x", rotation=45)
            annotate_bars(ax, fmt="{:.1f}")
            plt.tight_layout()
            fig.savefig(figs / "throughput.png", dpi=300)
            plt.close(fig)

        # 2c) Handshake latency by algorithm
        if "handshake_ms" in df:
            fig = plt.figure(figsize=(8, 5))
            ax = sns.boxplot(data=df, x="algorithm", y="handshake_ms")
            ax.set_title("Handshake Latency (ms) by Algorithm")
            ax.tick_params(axis="x", rotation=45)
            plt.tight_layout()
            fig.savefig(figs / "handshake_by_algo.png", dpi=300)
            plt.close(fig)

        # 2d) Throughput by algorithm
        if "throughput_rps" in df:
            fig = plt.figure(figsize=(8, 5))
            ax = sns.boxplot(data=df, x="algorithm", y="throughput_rps")
            ax.set_title("Throughput (RPS) by Algorithm")
            ax.tick_params(axis="x", rotation=45)
            plt.tight_layout()
            fig.savefig(figs / "throughput_by_algo.png", dpi=300)
            plt.close(fig)

        # 2e) Response time distribution
        if "response_time_s" in df:
            fig = plt.figure(figsize=(8, 5))
            ax = sns.violinplot(data=df, x="quantum_resistant", y="response_time_s")
            ax.set_title("Response Time Distribution")
            plt.tight_layout()
            fig.savefig(figs / "response_dist.png", dpi=300)
            plt.close(fig)

        # 2f) TTFB by suite (if present)
        if "ttfb_s" in df:
            fig = plt.figure(figsize=(8, 5))
            ax = sns.barplot(data=df, x="suite", y="ttfb_s")
            ax.set_title("TTFB (s) by Suite")
            ax.tick_params(axis="x", rotation=45)
            annotate_bars(ax, fmt="{:.3f}")
            plt.tight_layout()
            fig.savefig(figs / "ttfb_by_suite.png", dpi=300)
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
    if (
        df.implementation.nunique() > 1
        and "throughput_rps" in df
        and "handshake_ms" in df
    ):
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

    # === 5) Throughput vs Concurrency (if available) ===
    # Try to load raw bulk JSON to fetch concurrency and payload
    raw_dir = run_dir
    try_json = list(raw_dir.glob("bulk_*.json"))
    rows = []
    for j in try_json:
        try:
            js = pd.read_json(j)
            js["port"] = int(re.search(r"bulk_(\d+)\.json", j.name).group(1))
            rows.append(js)
        except Exception:
            pass
    if rows:
        jd = pd.concat(rows, ignore_index=True)
        if {"concurrency", "throughput_mb_s"}.issubset(jd.columns):
            fig = plt.figure(figsize=(8, 5))
            ax = sns.lineplot(
                data=jd, x="concurrency", y="throughput_mb_s", hue="port", marker="o"
            )
            ax.set_title("Bulk Throughput vs Concurrency")
            ax.set_ylabel("MB/s")
            plt.tight_layout()
            fig.savefig(figs / "throughput_vs_concurrency.png", dpi=300)
            plt.close(fig)

    # === 6) Micro → Macro correlation (AES only, if resource_*.json present) ===
    res_files = list(run_dir.glob("resource_*.json"))
    if res_files and "throughput_mb_s" in df and (df["suite"] == "x25519_aesgcm").any():
        try:
            res_df = pd.concat([pd.read_json(p) for p in res_files], ignore_index=True)
            if "throughput_mb_s" in res_df:
                micro_mb_s = res_df["throughput_mb_s"].astype(float).mean()
                tls_aes = df[df["suite"] == "x25519_aesgcm"].copy()
                tls_aes = tls_aes.dropna(
                    subset=["throughput_mb_s"]
                )  # MB/s already mapped if present
                if not tls_aes.empty:
                    x = [micro_mb_s] * len(tls_aes)
                    y = tls_aes["throughput_mb_s"].astype(float).tolist()
                    rho, p = spearmanr(x, y)
                    fig = plt.figure(figsize=(6, 5))
                    plt.scatter(x, y, alpha=0.6)
                    plt.xlabel("Microbench (AES speed) MB/s")
                    plt.ylabel("TLS Throughput (MB/s) — AES-GCM")
                    plt.title(f"Micro → Macro correlation (Spearman ρ: n/a)")
                    # With constant x, Spearman is undefined; still show scatter line
                    plt.tight_layout()
                    fig.savefig(figs / "micro_macro_correlation.png", dpi=300)
                    plt.close(fig)
        except Exception:
            pass

    # === 7) Render extras: bytes-on-the-wire table PNG and TTFB bar chart ===
    try:
        if bow_csv.exists():
            bow = pd.read_csv(bow_csv)
            if not bow.empty:
                fig = plt.figure(figsize=(8, 2 + 0.3 * len(bow)))
                ax = fig.add_subplot(111)
                ax.axis("off")
                tbl = ax.table(
                    cellText=bow.values,
                    colLabels=bow.columns.tolist(),
                    loc="center",
                    cellLoc="center",
                )
                tbl.auto_set_font_size(False)
                tbl.set_fontsize(8)
                tbl.scale(1, 1.2)
                fig.tight_layout()
                fig.savefig(figs / "bytes_on_wire.png", dpi=300, bbox_inches="tight")
                plt.close(fig)
    except Exception:
        pass

    try:
        ttfb_files = list(Path("results").glob("ttfb_*.json"))
        rows = []
        for p in ttfb_files:
            try:
                j = pd.read_json(p, typ="series")
                rows.append(
                    {
                        "port": int(j.get("port", p.stem.split("_")[-1])),
                        "ttfb_s": float(j.get("ttfb_s", 0.0)),
                        "total_s": float(j.get("avg_time", 0.0)),
                    }
                )
            except Exception:
                continue
        if rows:
            tf = pd.DataFrame(rows).sort_values("port")
            fig, ax = plt.subplots(1, 2, figsize=(10, 4))
            sns.barplot(data=tf, x="port", y="ttfb_s", ax=ax[0])
            ax[0].set_title("TTFB (s) by port")
            for container in ax[0].containers:
                ax[0].bar_label(container, fmt="{:.3f}", fontsize=8)
            sns.barplot(data=tf, x="port", y="total_s", ax=ax[1])
            ax[1].set_title("Total time (s) by port")
            for container in ax[1].containers:
                ax[1].bar_label(container, fmt="{:.3f}", fontsize=8)
            plt.tight_layout()
            fig.savefig(figs / "ttfb_by_port.png", dpi=300)
            plt.close(fig)
    except Exception:
        pass

    # Handshake percentiles + 95% CI and CDF
    if "handshake_ms" in df:
        g = df.groupby(["implementation", "suite"])["handshake_ms"]
        stats = g.describe(percentiles=[0.5, 0.95]).reset_index()

        ci_rows = []
        for (impl, suite), grp in df.dropna(subset=["handshake_ms"]).groupby(
            ["implementation", "suite"]
        ):
            x = grp["handshake_ms"].astype(float).values
            if len(x) > 1:
                m = x.mean()
                s = x.std(ddof=1)
                n = len(x)
                se = s / max(np.sqrt(n), 1)
                ci95 = 1.96 * se
            else:
                m = x.mean() if len(x) else np.nan
                ci95 = np.nan
            ci_rows.append(
                {"implementation": impl, "suite": suite, "mean": m, "ci95": ci95}
            )
        ci = pd.DataFrame(ci_rows)
        fig = plt.figure(figsize=(10, 6))
        ax = sns.barplot(data=ci, x="implementation", y="mean", hue="suite", ci=None)
        # add error bars
        for i, p in enumerate(ax.patches):
            impls = ci["implementation"].unique()
            # patches order: each impl repeated per hue
            idx = i
            y = p.get_height()
            # corresponding ci95
            row = ci.iloc[idx]
            if pd.notna(row.get("ci95", np.nan)):
                ax.errorbar(
                    x=p.get_x() + p.get_width() / 2,
                    y=y,
                    yerr=row["ci95"],
                    fmt="none",
                    ecolor="black",
                    capsize=3,
                )
        ax.set_title("Handshake: mean ±95% CI (ms)")
        ax.set_ylabel("ms")
        plt.tight_layout()
        fig.savefig(figs / "handshake_ci.png", dpi=300)
        plt.close(fig)

        suites = df["suite"].unique()
        for sname in suites:
            sub = df[df.suite == sname]
            if sub.empty:
                continue
            fig = plt.figure(figsize=(7, 5))
            for impl, grp in sub.groupby("implementation"):
                x = np.sort(grp["handshake_ms"].astype(float).values)
                y = np.linspace(0, 1, len(x), endpoint=True)
                if len(x):
                    plt.plot(x, y, label=impl)
            plt.title(f"Handshake CDF — {sname}")
            plt.xlabel("ms")
            plt.ylabel("CDF")
            plt.legend()
            plt.tight_layout()
            fig.savefig(figs / f"handshake_cdf_{sname}.png", dpi=300)
            plt.close(fig)

    # Throughput panels per payload and concurrency
    bulk_files = list(run_dir.glob("bulk_*.json"))
    bulk_rows = []
    for j in bulk_files:
        try:
            js = pd.read_json(j, typ="series")
            port = int(re.search(r"bulk_(\d+)\.json", j.name).group(1))
            bulk_rows.append(
                {
                    "port": port,
                    "throughput_mb_s": float(js.get("throughput_mb_s", np.nan)),
                    "throughput_rps": float(js.get("requests_per_second", np.nan)),
                    "avg_request_time_s": float(js.get("avg_request_time_s", np.nan)),
                    "payload_size_mb": float(js.get("payload_size_mb", np.nan)),
                    "concurrency": int(js.get("concurrency", 1)),
                }
            )
        except Exception:
            continue
    if bulk_rows:
        bd = pd.DataFrame(bulk_rows).dropna(subset=["throughput_mb_s"])

        payloads = sorted(bd["payload_size_mb"].unique())
        concs = sorted(bd["concurrency"].unique())
        nrow, ncol = max(len(concs), 1), max(len(payloads), 1)
        fig, axes = plt.subplots(
            nrow, ncol, figsize=(5 * ncol, 3.5 * nrow), squeeze=False
        )
        for i, c in enumerate(concs):
            for j, payload in enumerate(payloads):
                ax = axes[i][j]
                sub = bd[(bd.concurrency == c) & (bd.payload_size_mb == payload)]
                if sub.empty:
                    ax.set_axis_off()
                    continue
                sns.barplot(data=sub, x="port", y="throughput_mb_s", ax=ax)
                ax.set_title(f"Throughput MB/s (payload={payload}MB, c={c})")
                ax.set_xlabel("port")
                ax.set_ylabel("MB/s")
        plt.tight_layout()
        fig.savefig(figs / "throughput_panels.png", dpi=300)
        plt.close(fig)

        fig = plt.figure(figsize=(7, 5))
        ax = sns.barplot(
            data=bd, x="payload_size_mb", y="avg_request_time_s", hue="concurrency"
        )
        ax.set_title("Avg response time (s) vs payload")
        annotate_bars(ax, fmt="{:.3f}")
        plt.tight_layout()
        fig.savefig(figs / "response_time_vs_payload.png", dpi=300)
        plt.close(fig)

    # 0-RTT vs full POST (TTFB and total)
    simple_files = list(run_dir.glob("simple_*.json"))
    full_files = list(run_dir.glob("fullpost_*.json"))
    s_rows, f_rows = [], []
    for p in simple_files:
        try:
            js = pd.read_json(p, typ="series")
            port = int(re.search(r"simple_(\d+)\.json", p.name).group(1))
            s_rows.append(
                {"port": port, "simple_avg": float(js.get("avg_time", np.nan))}
            )
        except Exception:
            pass
    for p in full_files:
        try:
            js = pd.read_json(p, typ="series")
            port = int(re.search(r"fullpost_(\d+)\.json", p.name).group(1))
            f_rows.append({"port": port, "full_avg": float(js.get("avg_time", np.nan))})
        except Exception:
            pass
    if s_rows or f_rows:
        dfc = pd.merge(
            pd.DataFrame(s_rows), pd.DataFrame(f_rows), on="port", how="outer"
        )
        dfc = dfc.sort_values("port")
        fig, ax = plt.subplots(figsize=(8, 5))
        width = 0.35
        ports = dfc["port"].astype(int).tolist()
        idx = np.arange(len(ports))
        svals = dfc["simple_avg"].fillna(0).tolist()
        fvals = dfc["full_avg"].fillna(0).tolist()
        ax.bar(idx - width / 2, svals, width, label="0-RTT total")
        ax.bar(idx + width / 2, fvals, width, label="Full handshake+POST")
        ax.set_xticks(idx)
        ax.set_xticklabels(ports)
        ax.set_ylabel("seconds")
        ax.set_title("0-RTT vs Full POST")
        ax.legend()
        plt.tight_layout()
        fig.savefig(figs / "0rtt_vs_full.png", dpi=300)
        plt.close(fig)

    # Bulk distributions (hist/violin) from raw
    raw_txt = list((Path("results") / "raw").glob("bulk_*.txt"))
    if raw_txt:
        dist = []
        for p in raw_txt:
            try:
                vals = [float(x) for x in Path(p).read_text().splitlines() if x.strip()]
                port = int(re.search(r"bulk_(\d+)\.txt", p.name).group(1))
                for v in vals:
                    dist.append({"port": port, "time_s": v})
            except Exception:
                continue
        dd = pd.DataFrame(dist)
        for payload in sorted(bd["payload_size_mb"].unique()) if bulk_rows else [None]:
            fig = plt.figure(figsize=(10, 4))
            ax1 = plt.subplot(1, 2, 1)
            sns.histplot(data=dd, x="time_s", hue="port", bins=30, kde=False, ax=ax1)
            ax1.set_title("Bulk per-request time histogram")
            ax2 = plt.subplot(1, 2, 2)
            sns.violinplot(data=dd, x="port", y="time_s", ax=ax2)
            ax2.set_title("Bulk per-request time violin")
            plt.tight_layout()
            fig.savefig(figs / f"bulk_distributions.png", dpi=300)
            plt.close(fig)

    # === 12) NetEm profiles (if config.txt includes delay/loss) ===
    # This run-level, so here we only annotate present delay/loss into a small figure
    if run_dir.joinpath("config.txt").exists():
        try:
            txt = run_dir.joinpath("config.txt").read_text()
            m1 = re.search(r"delay=(\d+)ms", txt)
            m2 = re.search(r"loss=([\d.]+)", txt)
            delay = int(m1.group(1)) if m1 else 0
            loss = float(m2.group(1)) if m2 else 0
            fig = plt.figure(figsize=(4, 2))
            plt.text(0.01, 0.6, f"delay={delay} ms\nloss={loss*100:.2f}%", fontsize=12)
            plt.axis("off")
            plt.tight_layout()
            fig.savefig(figs / "netem_profile.png", dpi=200)
            plt.close(fig)
        except Exception:
            pass

    # Handshake percentiles + summary table
    if "handshake_ms" in df:
        try:
            tbl_rows = []
            for (impl, suite), grp in df.groupby(
                ["implementation", "suite"], sort=False
            ):
                vals = grp["handshake_ms"].astype(float).dropna().values
                if len(vals) == 0:
                    continue
                p50 = np.percentile(vals, 50)
                p95 = np.percentile(vals, 95)
                m = np.mean(vals)
                s = np.std(vals, ddof=1) if len(vals) > 1 else 0.0
                n = len(vals)
                ci95 = 1.96 * (s / np.sqrt(n)) if n > 1 else 0.0
                tbl_rows.append(
                    {
                        "implementation": impl,
                        "suite": suite,
                        "p50_ms": round(p50, 1),
                        "p95_ms": round(p95, 1),
                        "mean_ms": round(m, 1),
                        "ci95_ms": round(ci95, 1),
                        "n": n,
                    }
                )
            if tbl_rows:
                tdf = pd.DataFrame(tbl_rows)
                fig = plt.figure(figsize=(10, max(2, 0.4 * len(tdf) + 1)))
                ax = fig.add_subplot(111)
                ax.axis("off")
                ax.table(
                    cellText=tdf.values,
                    colLabels=tdf.columns,
                    loc="center",
                    cellLoc="center",
                )
                fig.tight_layout()
                fig.savefig(
                    figs / "handshake_p50_p95_ci_table.png",
                    dpi=300,
                    bbox_inches="tight",
                )
                plt.close(fig)
        except Exception:
            pass

    # Throughput tail latency (p95/p99) per payload and concurrency from raw
    try:
        raw_txt = list((Path("results") / "raw").glob("bulk_*.txt"))
        if raw_txt:
            # Build a mapping port->times
            port_to_times = {}
            for p in raw_txt:
                try:
                    port = int(re.search(r"bulk_(\d+)\.txt", p.name).group(1))
                    vals = [
                        float(x) for x in Path(p).read_text().splitlines() if x.strip()
                    ]
                    if vals:
                        port_to_times[port] = vals
                except Exception:
                    continue
            # Tail stats per port
            tail_rows = []
            for port, vals in port_to_times.items():
                p95 = np.percentile(vals, 95)
                p99 = np.percentile(vals, 99)
                tail_rows.append(
                    {
                        "port": port,
                        "p95_s": round(p95, 4),
                        "p99_s": round(p99, 4),
                        "n": len(vals),
                    }
                )
            if tail_rows:
                tdf = pd.DataFrame(tail_rows).sort_values("port")
                fig = plt.figure(figsize=(6, max(2, 0.4 * len(tdf) + 1)))
                ax = fig.add_subplot(111)
                ax.axis("off")
                ax.table(
                    cellText=tdf.values,
                    colLabels=tdf.columns,
                    loc="center",
                    cellLoc="center",
                )
                fig.tight_layout()
                fig.savefig(
                    figs / "throughput_tail_latency_table.png",
                    dpi=300,
                    bbox_inches="tight",
                )
                plt.close(fig)
                # Add a short note file
                note = figs / "throughput_tail_latency_note.txt"
                note.write_text(
                    "Tail latency (p95/p99) computed from per-request times. Larger payloads and higher concurrency typically increase tails; consider P2/P3 profiles for stress."
                )
    except Exception:
        pass

    # PQ negotiated group evidence (instructions saved to txt)
    try:
        pq_note = figs / "pq_negotiation_howto.txt"
        pq_note.write_text(
            "OpenSSL/8443:\n"
            '  docker exec tls-perf-nginx sh -lc "/usr/local/bin/openssl s_client -trace -tls1_3 -provider default -provider oqsprovider -groups X25519MLKEM768 -CAfile /etc/nginx/certs/ca.pem -connect ${HOST:-host.docker.internal}:8443 </dev/null"\n\n'
            "wolfSSL/11112: (verbose keyshare)\n"
            '  docker exec wolfssl-cli sh -lc "/usr/local/bin/wolf-client -h wolfssl-server-kyber -p 11112 -v 4 --pqc X25519_ML_KEM_768 -d"\n\n'
            "Zrzut ekranu z linii KeyShare/NamedGroup wstaw do aneksu."
        )
    except Exception:
        pass


def main():
    args = parse_args()
    run_dir = Path(args.run)
    df_raw, netem = load_data(run_dir)
    df = prepare_data(df_raw)
    create_visualizations(df, run_dir, args.separate)
    print(f"✓ Wykresy zapisane w: figures/{run_dir.name}/analyze")


if __name__ == "__main__":
    main()
