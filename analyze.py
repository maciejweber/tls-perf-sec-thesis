#!/usr/bin/env python3
# pip install pandas numpy scipy matplotlib seaborn openpyxl statsmodels

from __future__ import annotations
from pathlib import Path
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from scipy import stats
import sys
import json
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
    netem_file = run_dir / "netem.txt"
    if netem_file.exists():
        df["netem_enabled"] = True
        with open(netem_file) as f:
            c = f.read()
            if "delay=" in c:
                delay = c.split("delay=")[1].split("ms")[0]
                df["netem_delay_ms"] = int(delay)
            else:
                df["netem_delay_ms"] = 0
            if "loss=" in c:
                loss = c.split("loss=")[1].split("\n")[0]
                df["netem_loss"] = float(loss)
            else:
                df["netem_loss"] = 0.0
    else:
        df["netem_enabled"] = False
        df["netem_delay_ms"] = 0
        df["netem_loss"] = 0.0
    return df


def load_perf_data(run_dir: Path) -> pd.DataFrame:
    perf_files = list(run_dir.glob("perf_*.json"))
    records: list[dict] = []
    for pf in perf_files:
        parts = pf.stem.split("_")
        if len(parts) < 3:
            continue
        # format: perf_<port>_<timestamp>.json  or perf_<port>_<run>.json
        port = parts[1]
        # assume the JSON has fields: port, mean_time_ms, cpu_cycles, cpu_instructions, package_watts
        with open(pf) as f:
            data = json.load(f)
        base = {
            "implementation": None,
            "suite": None,
            "run": None,
        }
        # infer implementation and suite from filename not possible—bench.csv has context.
        # Instead, perf JSON only contains port, so we will match by port after reading bench.csv.
        # We'll attach port here and later merge on port and run number.
        rec = {
            "port": int(data.get("port", 0)),
            "run": None,
            "mean_time_ms": data.get("mean_time_ms", 0),
            "cpu_cycles": data.get("cpu_cycles", 0),
            "cpu_instructions": data.get("cpu_instructions", 0),
            "package_watts": data.get("package_watts", 0),
        }
        records.append(rec)
    return pd.DataFrame(records)


def merge_perf_into_raw(raw: pd.DataFrame, perf: pd.DataFrame) -> pd.DataFrame:
    if perf.empty:
        return raw
    # w raw mamy kolumnę "metric","value","suite","implementation","run"
    # w perf mamy "port","run","cpu_cycles","cpu_instructions","package_watts"
    # znajdź mapping port → suite,implementation,run  z raw gdzie test=="bulk"
    bulk_rows = raw[raw.test == "bulk"][
        ["implementation", "suite", "run", "value"]
    ].copy()
    # ale "value" w bulk to RPS, nie potrzebujemy. W raw nie ma kolumny port, więc najpierw z bench.csv nie ma port.
    # Przyjmijmy uproszczenie: perf pliki są generowane **tuż po** bulk dla tej samej iteracji,
    # a run_dir struktura: perf_<port>_<timestamp>.json, więc nie mamy run numeru. Zatem: pominiemy precyzyjne mapowanie i
    # zakładamy, że kolejność perf_files odpowiada kolejności wpisów "bulk" w raw.
    bulk_indices = raw[(raw.test == "bulk") & (raw.metric == "rps")].index.to_list()
    perf = perf.reset_index(drop=True)
    if len(perf) != len(bulk_indices):
        # jeśli nie pasuje długość, zwracamy raw bez merge
        return raw
    perf_rows: list[dict] = []
    for i, idx in enumerate(bulk_indices):
        impl = raw.at[idx, "implementation"]
        suite = raw.at[idx, "suite"]
        run = raw.at[idx, "run"]
        for m in ["cpu_cycles", "cpu_instructions", "package_watts"]:
            perf_rows.append(
                {
                    "implementation": impl,
                    "suite": suite,
                    "test": "perf",
                    "run": run,
                    "metric": m,
                    "value": perf.at[i, m],
                    "unit": (
                        "cycles"
                        if m == "cpu_cycles"
                        else ("instr" if m == "cpu_instructions" else "W")
                    ),
                    "run_timestamp": raw.at[idx, "run_timestamp"],
                    "netem_enabled": raw.at[idx, "netem_enabled"],
                    "netem_delay_ms": raw.at[idx, "netem_delay_ms"],
                    "netem_loss": raw.at[idx, "netem_loss"],
                }
            )
    perf_df = pd.DataFrame(perf_rows)
    return pd.concat([raw, perf_df], ignore_index=True)


def load_all_runs() -> pd.DataFrame:
    run_dirs = sorted(RESULTS_DIR.glob("run_*"))
    if not run_dirs:
        raise FileNotFoundError("Brak folderów run_* w results/")
    frames: list[pd.DataFrame] = []
    for run_dir in run_dirs:
        try:
            df = load_csv_from_run(run_dir)
            perf = load_perf_data(run_dir)
            merged = merge_perf_into_raw(df, perf)
            frames.append(merged)
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
    # Oblicz efektywność energetyczną
    if df.metric.eq("package_watts").any() and df.metric.eq("throughput_mb_s").any():
        pw = df[df.metric == "package_watts"].copy()
        tp = df[df.metric == "throughput_mb_s"].copy()
        merged = pd.merge(
            tp[["implementation", "suite", "run", "value"]],
            pw[["implementation", "suite", "run", "value"]],
            on=["implementation", "suite", "run"],
            suffixes=("_throughput", "_power"),
        )
        if not merged.empty:
            eff = merged.copy()
            eff["value"] = merged["value_throughput"] / merged["value_power"]
            eff["metric"] = "efficiency_mb_per_joule"
            eff["unit"] = "MB/J"
            eff["test"] = "perf"
            for col in [
                "run_timestamp",
                "netem_enabled",
                "netem_delay_ms",
                "netem_loss",
            ]:
                if col in df.columns:
                    eff[col] = pw[col].iloc[0] if col in pw.columns else None
            df = pd.concat([df, eff], ignore_index=True)
    return df


def summarise(df: pd.DataFrame) -> pd.DataFrame:
    metrics_of_interest = [
        "handshake_ms",
        "throughput_mb_s",
        "response_time_s",
        "rps",
        "cpu_cycles",
        "cpu_instructions",
        "package_watts",
        "efficiency_mb_per_joule",
    ]
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
                ("ci95", lambda s: stats.sem(s) * 1.96 if len(s) > 1 else 0),
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
    if d["implementation"].nunique() < 2 or d["suite"].nunique() < 2:
        print("[2-way ANOVA] Za mało kategorii do analizy")
        return
    counts = d.groupby(["implementation", "suite"]).size()
    if (counts < 2).any():
        print("[2-way ANOVA] Wymagane co najmniej 2 obserwacje w każdej komórce")
        return
    try:
        model = ols(
            "value ~ C(implementation) + C(suite) + C(implementation):C(suite)",
            data=d,
        ).fit()
        if model.df_resid <= 0 or np.isinf(model.ssr):
            print("[2-way ANOVA] Zbyt mało danych, pomijam")
            return
        aov = sm.stats.anova_lm(model, typ=2)
        print("\n[2-way ANOVA] throughput_mb_s\n", aov, "\n")
    except Exception as e:
        print(f"[2-way ANOVA] Błąd: {e}")


def plot_handshake_comparison(df: pd.DataFrame):
    sub = df[df.metric == "handshake_ms"]
    if sub.empty:
        print("⚠ Brak danych handshake_ms dla wykresu")
        return
    plt.figure(figsize=(10, 6))
    sns.violinplot(
        x="suite", y="value", hue="implementation", data=sub, inner="quartile"
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


def plot_energy_efficiency(summary: pd.DataFrame):
    data = summary[summary.metric == "efficiency_mb_per_joule"]
    if data.empty:
        print("⚠ Brak danych efficiency_mb_per_joule dla wykresu")
        return
    pivot = data.pivot(index="implementation", columns="suite", values="mean")
    fig, ax = plt.subplots(figsize=(10, 6))
    pivot.plot(kind="bar", ax=ax)
    ax.set_ylabel("Energy Efficiency [MB/J]")
    ax.set_xlabel("Implementation")
    ax.set_title("Energy Efficiency Comparison")
    ax.legend(title="Cipher Suite")
    ax.grid(True, alpha=0.3, axis="y")
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.savefig(FIG_DIR / "energy_efficiency.png", dpi=300)
    plt.close()


def plot_cpu_usage(summary: pd.DataFrame):
    data_cycles = summary[summary.metric == "cpu_cycles"]
    data_instructions = summary[summary.metric == "cpu_instructions"]
    if data_cycles.empty and data_instructions.empty:
        print("⚠ Brak danych CPU dla wykresu")
        return
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 6))
    if not data_cycles.empty:
        pivot_cycles = data_cycles.pivot(
            index="implementation", columns="suite", values="mean"
        )
        pivot_cycles.plot(kind="bar", ax=ax1)
        ax1.set_ylabel("CPU Cycles")
        ax1.set_title("CPU Cycles per Operation")
        ax1.legend(title="Cipher Suite")
        ax1.grid(True, alpha=0.3, axis="y")
    if not data_instructions.empty:
        pivot_inst = data_instructions.pivot(
            index="implementation", columns="suite", values="mean"
        )
        pivot_inst.plot(kind="bar", ax=ax2)
        ax2.set_ylabel("Instructions")
        ax2.set_title("Instructions per Operation")
        ax2.legend(title="Cipher Suite")
        ax2.grid(True, alpha=0.3, axis="y")
    plt.tight_layout()
    plt.savefig(FIG_DIR / "cpu_usage.png", dpi=300)
    plt.close()


def plot_netem_impact(df: pd.DataFrame):
    if not df["netem_enabled"].any():
        print("⚠ Brak danych NetEm dla wykresu")
        return
    data = df[df.metric == "throughput_mb_s"].copy()
    if data.empty:
        return
    data["condition"] = data["netem_enabled"].map(
        {True: "With NetEm", False: "Without NetEm"}
    )
    plt.figure(figsize=(10, 6))
    sns.boxplot(x="suite", y="value", hue="condition", data=data)
    plt.ylabel("Throughput [MB/s]")
    plt.xlabel("Cipher Suite")
    plt.title("Impact of Network Conditions on Throughput")
    plt.legend(title="Network Condition")
    plt.grid(True, alpha=0.3, axis="y")
    plt.tight_layout()
    plt.savefig(FIG_DIR / "netem_impact.png", dpi=300)
    plt.close()


def to_excel(
    summary: pd.DataFrame,
    raw: pd.DataFrame,
    run_dir: Path,
    perf_data: pd.DataFrame = None,
):
    excel_path = run_dir / "analysis_results.xlsx"
    with pd.ExcelWriter(excel_path, engine="openpyxl") as writer:
        summary.to_excel(writer, sheet_name="Summary", index=False)
        for metric in summary.metric.unique():
            sheet_name = metric[:31]
            summary[summary.metric == metric].to_excel(
                writer, sheet_name=sheet_name, index=False
            )
        if perf_data is not None and not perf_data.empty:
            perf_data.to_excel(writer, sheet_name="Performance", index=False)
        if "netem_enabled" in raw.columns and raw["netem_enabled"].any():
            netem_analysis = (
                raw[raw["netem_enabled"]]
                .groupby(["implementation", "suite", "test", "metric"])["value"]
                .agg(["mean", "std", "count"])
                .reset_index()
            )
            netem_analysis.to_excel(writer, sheet_name="NetEm Analysis", index=False)
        raw.head(1000).to_excel(writer, sheet_name="Raw Data", index=False)
        info_df = pd.DataFrame(
            {
                "Info": [
                    "Analysis Date",
                    "Source Folder",
                    "Total Samples",
                    "NetEm Used",
                ],
                "Value": [
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    run_dir.name,
                    len(raw),
                    (
                        "Yes"
                        if raw.get("netem_enabled", pd.Series([False])).any()
                        else "No"
                    ),
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
            perf = load_perf_data(run_dir)
            raw = merge_perf_into_raw(raw, perf)
    else:
        run_dir = find_latest_run()
        print(f"📊 Analiza najnowszego: {run_dir.name}")
        raw = load_csv_from_run(run_dir)
        perf = load_perf_data(run_dir)
        raw = merge_perf_into_raw(raw, perf)

    perf_data = load_perf_data(run_dir) if run_dir != RESULTS_DIR else pd.DataFrame()
    tidy = rename_or_compute_metrics(raw)
    summary = summarise(tidy)

    print("\n📈 Statystyki opisowe:")
    print(summary.groupby("metric")[["mean", "std"]].mean().round(2))

    if "netem_enabled" in raw.columns and raw["netem_enabled"].any():
        delay = int(raw[raw["netem_enabled"]]["netem_delay_ms"].iloc[0])
        loss = float(raw[raw["netem_enabled"]]["netem_loss"].iloc[0])
        print(f"\n🌐 NetEm włączony: delay={delay}ms, loss={loss*100}%")

    print("\n📈 Testy ANOVA:")
    for m in ["handshake_ms", "throughput_mb_s"]:
        one_way_anova(tidy, m)
    two_way_anova(tidy)

    print("\n📊 Generowanie wykresów...")
    plot_handshake_comparison(tidy)
    plot_throughput_bars(tidy, summary)
    plot_performance_heatmap(summary)
    if not summary[summary.metric == "efficiency_mb_per_joule"].empty:
        plot_energy_efficiency(summary)
    if not summary[summary.metric.isin(["cpu_cycles", "cpu_instructions"])].empty:
        plot_cpu_usage(summary)
    if "netem_enabled" in tidy.columns and tidy["netem_enabled"].any():
        plot_netem_impact(tidy)

    to_excel(summary, raw, run_dir, perf_data)

    print("\n✅ Analiza ukończona!")
    print(f"📁 Wykresy: {FIG_DIR.relative_to(Path.cwd())}")
    print(f"📁 Excel: {run_dir.name}/analysis_results.xlsx")

    if not perf_data.empty:
        print("\n⚡ Podsumowanie wydajności:")
        perf_summary = (
            perf_data[["cpu_cycles", "package_watts", "port"]].groupby(["port"]).mean()
        )
        print(perf_summary.round(2))


if __name__ == "__main__":
    main()
