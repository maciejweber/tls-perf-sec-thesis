#!/usr/bin/env python3
# pip install pandas numpy scipy matplotlib seaborn openpyxl

from __future__ import annotations
from pathlib import Path
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from scipy import stats
import sys
from datetime import datetime

RESULTS_DIR = Path(__file__).resolve().parent / "results"
FIG_DIR = Path(__file__).resolve().parent / "figures"
FIG_DIR.mkdir(exist_ok=True)


def find_latest_run() -> Path:
    latest = RESULTS_DIR / "latest"
    if latest.exists() and latest.is_symlink():
        return latest.resolve()
    run_dirs = sorted(RESULTS_DIR.glob("run_*"), reverse=True)
    if run_dirs:
        return run_dirs[0]
    raise FileNotFoundError("Brak folderów run_* w results/")


def load_csv_from_run(run_dir: Path) -> pd.DataFrame:
    csv_path = run_dir / "bench.csv"
    if not csv_path.exists():
        raise FileNotFoundError(f"Brak {csv_path}")
    df = pd.read_csv(csv_path)
    df["run_timestamp"] = run_dir.name.replace("run_", "")
    return df


def load_all_runs() -> pd.DataFrame:
    run_dirs = sorted(RESULTS_DIR.glob("run_*"))
    if not run_dirs:
        raise FileNotFoundError("Brak folderów run_* w results/")
    frames: list[pd.DataFrame] = []
    for run_dir in run_dirs:
        try:
            df = load_csv_from_run(run_dir)
            frames.append(df)
            print(f"✓ Wczytano: {run_dir.name}")
        except Exception as e:
            print(f"⚠ Pomijam {run_dir.name}: {e}")
    return pd.concat(frames, ignore_index=True)


def rename_or_compute_metrics(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.loc[(df.metric == "mean_ms") & (df.test == "handshake"), "metric"] = (
        "handshake_ms"
    )
    df.loc[
        (df.metric == "mean_time_s") & (df.test.isin(["bulk", "0rtt"])), "metric"
    ] = "response_time_s"
    SIZE_MB = 1.0
    if not df.metric.eq("throughput_mb_s").any():
        bulk_rps = df[(df.metric == "rps") & (df.test == "bulk")].copy()
        if not bulk_rps.empty:
            bulk_rps["value"] = bulk_rps.value.astype(float) * SIZE_MB
            bulk_rps["metric"] = "throughput_mb_s"
            bulk_rps["unit"] = "MB/s"
            df = pd.concat([df, bulk_rps], ignore_index=True)
    return df


def summarise(df: pd.DataFrame) -> pd.DataFrame:
    metrics_of_interest = ["handshake_ms", "throughput_mb_s", "response_time_s", "rps"]
    df_filtered = df[df.metric.isin(metrics_of_interest)]
    summary = (
        df_filtered.groupby(["implementation", "suite", "test", "metric"])["value"]
        .agg(
            [
                ("mean", "mean"),
                ("std", "std"),
                ("min", "min"),
                ("max", "max"),
                ("p95", lambda s: s.quantile(0.95)),
                (
                    "ci95",
                    lambda s: stats.sem(s) * 1.96 if len(s) > 1 else 0,
                ),
                ("n", "count"),
            ]
        )
        .reset_index()
    )
    return summary


def one_way_anova(df: pd.DataFrame, metric: str):
    sub = df[df.metric == metric]
    if sub.empty:
        print(f"[1-way] Brak danych dla {metric}")
        return
    groups = [g.value.values for _, g in sub.groupby("suite")]
    if len(groups) < 2 or any(len(g) < 2 for g in groups):
        print(f"[1-way] Za mało danych dla {metric}")
        return
    f, p = stats.f_oneway(*groups)
    print(f"[1-way] {metric}: F={f:.2f}, p={p:.4g}")


def two_way_anova(df: pd.DataFrame):
    try:
        import statsmodels.api as sm
        from statsmodels.formula.api import ols
    except ImportError:
        print("▶ Zainstaluj statsmodels dla 2-way ANOVA: pip install statsmodels")
        return
    d = df[df.metric == "throughput_mb_s"].dropna(subset=["value"])
    if d.empty:
        print("[2-way ANOVA] Brak danych throughput_mb_s")
        return
    counts = d.groupby(["implementation", "suite"]).size()
    if (counts < 2).any():
        print("[2-way ANOVA] Wymagane co najmniej 2 obserwacje w każdej komórce")
        return
    model = ols(
        "value ~ C(implementation) + C(suite) + C(implementation):C(suite)",
        data=d,
    ).fit()
    if model.df_resid <= 0 or np.isinf(model.ssr):
        print("[2-way ANOVA] Zbyt mało stopni swobody, pomijam")
        return
    aov = sm.stats.anova_lm(model, typ=2)
    print("\n[2-way ANOVA] throughput_mb_s\n", aov, "\n")


def plot_handshake_comparison(df: pd.DataFrame):
    sub = df[df.metric == "handshake_ms"]
    if sub.empty:
        print("⚠ Brak danych handshake_ms dla wykresu")
        return
    plt.figure(figsize=(10, 6))
    sns.violinplot(
        x="suite",
        y="value",
        hue="implementation",
        data=sub,
        split=False,
        inner="quartile",
    )
    plt.ylabel("Handshake time [ms]")
    plt.xlabel("Cipher Suite")
    plt.title("TLS Handshake Performance Comparison")
    plt.yscale("log")
    plt.grid(True, alpha=0.3, axis="y")
    plt.tight_layout()
    plt.savefig(FIG_DIR / "handshake_comparison.png", dpi=300)
    plt.close()


def plot_throughput_bars(df: pd.DataFrame, summary: pd.DataFrame):
    data = summary[summary.metric == "throughput_mb_s"]
    if data.empty:
        print("⚠ Brak danych throughput_mb_s dla wykresu")
        return
    pivot = data.pivot(index="implementation", columns="suite", values="mean")
    errors = data.pivot(index="implementation", columns="suite", values="ci95")
    fig, ax = plt.subplots(figsize=(10, 6))
    x = np.arange(len(pivot.index))
    width = 0.25
    for i, suite in enumerate(pivot.columns):
        offset = (i - 1) * width
        ax.bar(
            x + offset,
            pivot[suite],
            width,
            label=suite,
            yerr=errors[suite] if not errors.empty else None,
            capsize=5,
        )
    ax.set_xlabel("Implementation")
    ax.set_ylabel("Throughput [MB/s]")
    ax.set_title("TLS Bulk Transfer Performance")
    ax.set_xticks(x)
    ax.set_xticklabels(pivot.index)
    ax.legend()
    ax.grid(True, alpha=0.3, axis="y")
    plt.tight_layout()
    plt.savefig(FIG_DIR / "throughput_comparison.png", dpi=300)
    plt.close()


def plot_performance_heatmap(summary: pd.DataFrame):
    data = summary[summary.metric == "handshake_ms"]
    if data.empty:
        print("⚠ Brak danych handshake_ms dla heatmapy")
        return
    pivot = data.pivot(index="implementation", columns="suite", values="mean")
    if "openssl" in pivot.index:
        normalized = pivot.div(pivot.loc["openssl"], axis=1)
    else:
        normalized = pivot
    plt.figure(figsize=(8, 5))
    sns.heatmap(
        normalized,
        annot=True,
        fmt=".2f",
        cmap="RdYlGn_r",
        center=1.0,
        cbar_kws={"label": "Relative time (lower is better)"},
    )
    plt.title("Handshake Performance Relative to OpenSSL")
    plt.tight_layout()
    plt.savefig(FIG_DIR / "performance_heatmap.png", dpi=300)
    plt.close()


def to_excel(summary: pd.DataFrame, raw: pd.DataFrame, run_dir: Path):
    excel_path = run_dir / "analysis_results.xlsx"
    with pd.ExcelWriter(excel_path, engine="openpyxl") as writer:
        summary.to_excel(writer, sheet_name="Summary", index=False)
        for metric in summary.metric.unique():
            metric_data = summary[summary.metric == metric]
            sheet_name = metric[:31]
            metric_data.to_excel(writer, sheet_name=sheet_name, index=False)
        raw.head(1000).to_excel(writer, sheet_name="Raw Data", index=False)
        info_df = pd.DataFrame(
            {
                "Info": ["Analysis Date", "Source Folder", "Total Samples"],
                "Value": [
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    run_dir.name,
                    len(raw),
                ],
            }
        )
        info_df.to_excel(writer, sheet_name="Info", index=False)
    try:
        rel = excel_path.resolve().relative_to(Path.cwd().resolve())
    except ValueError:
        rel = excel_path
    print(f"✓ Excel zapisany: {rel}")


def main():
    if len(sys.argv) > 1:
        if sys.argv[1] == "--all":
            print("📊 Analiza wszystkich folderów run_*")
            raw = load_all_runs()
            run_dir = RESULTS_DIR
        else:
            run_dir = RESULTS_DIR / sys.argv[1]
            if not run_dir.exists():
                print(f"❌ Nie znaleziono: {run_dir}")
                sys.exit(1)
            print(f"📊 Analiza: {run_dir.name}")
            raw = load_csv_from_run(run_dir)
    else:
        run_dir = find_latest_run()
        print(f"📊 Analiza najnowszego: {run_dir.name}")
        raw = load_csv_from_run(run_dir)
    tidy = rename_or_compute_metrics(raw)
    summary = summarise(tidy)
    print("\n📈 Statystyki opisowe:")
    print(summary.groupby("metric")[["mean", "std"]].mean().round(2))
    print("\n📈 Testy ANOVA:")
    for m in ["handshake_ms", "throughput_mb_s"]:
        one_way_anova(tidy, m)
    two_way_anova(tidy)
    print("\n📊 Generowanie wykresów...")
    plot_handshake_comparison(tidy)
    plot_throughput_bars(tidy, summary)
    plot_performance_heatmap(summary)
    to_excel(summary, raw, run_dir)
    print("\n✅ Analiza ukończona!")
    print(f"📁 Wykresy: {FIG_DIR.relative_to(Path.cwd())}")
    print(f"📁 Excel: {run_dir.name}/analysis_results.xlsx")


if __name__ == "__main__":
    main()
