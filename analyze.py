#!/usr/bin/env python3
# pip install pandas numpy scipy matplotlib seaborn openpyxl

"""
Rozdział 10 – analiza wydajności TLS  (wersja rozszerzona)
----------------------------------------------------------
+ 2-way ANOVA  (implementation × suite)
+ violin-plot dla handshake
+ heat-mapa średniego throughputu
"""

from __future__ import annotations
from pathlib import Path
import pandas as pd, numpy as np, matplotlib.pyplot as plt, seaborn as sns
from scipy import stats, stats as sc

RESULTS_DIR = Path(__file__).resolve().parent / "results"
FIG_DIR = Path(__file__).resolve().parent / "figures"
FIG_DIR.mkdir(exist_ok=True)


# ---------- 1. I/O -----------------------------------------------------------
def load_all_csv(folder=RESULTS_DIR) -> pd.DataFrame:
    frames = [pd.read_csv(f).assign(source=f.name) for f in folder.glob("*.csv")]
    if not frames:
        raise FileNotFoundError(f"Brak csv w {folder}")
    return pd.concat(frames, ignore_index=True)


def rename_or_compute_metrics(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.loc[df.metric.eq("mean_ms") & df.test.eq("handshake"), "metric"] = "handshake_ms"
    SIZE_MB = 1.0
    if not df.metric.eq("throughput_mb_s").any():
        df2 = df[df.metric.eq("rps") & df.test.eq("bulk")].copy()
        df2["value"] = df2.value.astype(float) * SIZE_MB
        df2["metric"] = "throughput_mb_s"
        df = pd.concat([df, df2])
    return df


# ---------- 2. Statystyki opisowe -------------------------------------------
def summarise(df):
    df = df[df.metric.isin(["handshake_ms", "throughput_mb_s"])]
    return (
        df.groupby(["implementation", "suite", "test", "metric"])
        .value.agg(
            mean="mean",
            p95=lambda s: s.quantile(0.95),
            ci95=lambda s: stats.sem(s) * 1.96 if len(s) > 1 else 0,
        )
        .reset_index()
    )


# ---------- 3. ANOVA ---------------------------------------------------------
def one_way_anova(df, metric):
    sub = df[df.metric.eq(metric)]
    f, p = stats.f_oneway(*[g.value for _, g in sub.groupby("suite")])
    print(f"[1-way] {metric}: F={f:.2f}, p={p:.4g}")


def two_way_anova(df):
    """Szybka 2-way ANOVA (korzystamy z statsmodels, jeśli dostępny)."""
    try:
        import statsmodels.api as sm
        from statsmodels.formula.api import ols
    except ImportError:
        print("▶ pydoc: pip install statsmodels → dostaniesz 2-way ANOVA\n")
        return

    d = df[df.metric.eq("throughput_mb_s")]
    model = ols(
        "value ~ C(implementation) + C(suite) + C(implementation):C(suite)", data=d
    ).fit()
    aov = sm.stats.anova_lm(model, typ=2)
    print("\n[2-way ANOVA] throughput_mb_s\n", aov, "\n")


# ---------- 4. Wykresy -------------------------------------------------------
def plot_violin(df):
    sub = df[df.metric.eq("handshake_ms")]
    plt.figure(figsize=(8, 4))
    sns.violinplot(x="suite", y="value", hue="implementation", data=sub, split=True)
    plt.ylabel("handshake [ms]")
    plt.xlabel("suite")
    plt.tight_layout()
    plt.savefig(FIG_DIR / "handshake_violin.png", dpi=300)
    plt.close()


def plot_throughput_box(df):
    sub = df[df.metric.eq("throughput_mb_s")]
    plt.figure(figsize=(8, 5))
    sns.boxplot(x="suite", y="value", data=sub)
    plt.savefig(FIG_DIR / "throughput_box.png", dpi=300)
    plt.close()


def plot_heatmap(summary):
    pivot = summary.query("metric=='throughput_mb_s' and test=='bulk'").pivot(
        index="implementation", columns="suite", values="mean"
    )
    plt.figure(figsize=(4, 3))
    sns.heatmap(pivot, annot=True, fmt=".1f", cbar=False)
    plt.title("Średni throughput [MB/s]")
    plt.tight_layout()
    plt.savefig(FIG_DIR / "throughput_heatmap.png", dpi=300)
    plt.close()


# ---------- 5. Excel ---------------------------------------------------------
# --- 5. Excel ---------------------------------------------------------
def to_excel(summary, out: Path = RESULTS_DIR / "summary.xlsx"):
    with pd.ExcelWriter(out) as xls:
        for m, g in summary.groupby("metric"):
            g.drop(columns="metric").to_excel(xls, sheet_name=m[:31], index=False)


# ---------- main -------------------------------------------------------------
def main():
    raw = load_all_csv()
    tidy = rename_or_compute_metrics(raw)
    summary = summarise(tidy)

    print("\nOpisowe:\n", summary.head(), "\n")
    for m in ["handshake_ms", "throughput_mb_s"]:
        one_way_anova(tidy, m)
    two_way_anova(tidy)

    plot_violin(tidy)
    plot_throughput_box(tidy)
    plot_heatmap(summary)
    to_excel(summary)
    print(
        f"✔ Analiza ukończona – summary zapisano w { (RESULTS_DIR / 'summary.xlsx').relative_to(Path.cwd()) }"
    )


if __name__ == "__main__":
    main()
