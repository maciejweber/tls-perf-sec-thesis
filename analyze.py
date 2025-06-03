#!/usr/bin/env python3
"""
Enhanced analysis with CPU cycles per byte
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
import json
import sys
from scipy import stats
from statsmodels.stats.anova import anova_lm
from statsmodels.formula.api import ols
import warnings

warnings.filterwarnings("ignore")


def load_latest_results():
    """Load results from latest/ symlink"""
    results_dir = Path("results")
    latest_link = results_dir / "latest"

    if not latest_link.exists():
        print("❌ Brak results/latest - uruchom najpierw benchmarki")
        sys.exit(1)

    run_dir = latest_link.resolve()
    print(f"📊 Analiza najnowszego: {run_dir.name}")

    # Load main CSV
    csv_path = run_dir / "bench.csv"
    if not csv_path.exists():
        print(f"❌ Brak {csv_path}")
        sys.exit(1)

    df = pd.read_csv(csv_path)

    # Load config for NetEm info
    config_path = run_dir / "config.txt"
    netem_info = {"delay": 0, "loss": 0.0}
    if config_path.exists():
        with open(config_path) as f:
            content = f.read()
            if "delay=" in content:
                import re

                delay_match = re.search(r"delay=(\d+)ms", content)
                loss_match = re.search(r"loss=([\d.]+)", content)
                if delay_match:
                    netem_info["delay"] = int(delay_match.group(1))
                if loss_match:
                    netem_info["loss"] = float(loss_match.group(1))

    return df, run_dir, netem_info


def prepare_data(df):
    """Prepare and pivot data with enhanced metrics"""

    # Map metrics to more readable names
    metric_mapping = {
        "mean_ms": "handshake_ms",
        "requests_per_second": "rps",
        "mean_time_s": "response_time_s",
        "package_watts": "package_watts",
        "cpu_cycles_per_byte": "cpu_cycles_per_byte",
        "energy_efficiency_mb_per_joule": "efficiency_mb_per_joule",
        "resource_mean_ms": "crypto_operation_ms",
        "cpu_cycles": "total_cpu_cycles",
    }

    # Apply mapping
    df["metric_clean"] = df["metric"].map(metric_mapping).fillna(df["metric"])

    # Pivot to wide format
    pivot = df.pivot_table(
        index=["implementation", "suite", "test", "run"],
        columns="metric_clean",
        values="value",
        aggfunc="first",
    ).reset_index()

    # Calculate derived metrics
    if "rps" in pivot.columns:
        pivot["throughput_mb_s"] = pivot["rps"] * 1.0  # Assume ~1MB per request

    # Port mapping for grouping
    pivot["port"] = pivot["suite"].map(
        {"x25519_aesgcm": 4431, "chacha20": 4432, "kyber_hybrid": 8443}
    )

    return pivot


def statistical_analysis(df):
    """Enhanced statistical analysis with new metrics"""
    print("\n📈 Statystyki opisowe:")

    # Focus on key metrics
    key_metrics = [
        "handshake_ms",
        "throughput_mb_s",
        "response_time_s",
        "package_watts",
        "cpu_cycles_per_byte",
        "efficiency_mb_per_joule",
    ]

    available_metrics = [m for m in key_metrics if m in df.columns]
    if available_metrics:
        desc_stats = df[available_metrics].describe()
        print(desc_stats.loc[["mean", "std"]].round(2))

    print(f"\n📈 Testy ANOVA:")

    # Test each metric
    for metric in available_metrics:
        if df[metric].notna().sum() > 10:  # Need enough data points
            try:
                # 1-way ANOVA by suite
                groups = [group[metric].dropna() for name, group in df.groupby("suite")]
                groups = [g for g in groups if len(g) > 1]

                if len(groups) >= 2:
                    f_stat, p_val = stats.f_oneway(*groups)
                    print(f"[1-way] {metric}: F={f_stat:.2f}, p={p_val:.3e}")
            except Exception as e:
                print(f"⚠️  ANOVA failed for {metric}: {e}")

    # 2-way ANOVA for throughput if available
    if "throughput_mb_s" in df.columns and df["throughput_mb_s"].notna().sum() > 10:
        try:
            print(f"\n[2-way ANOVA] throughput_mb_s")
            model = ols(
                "throughput_mb_s ~ C(implementation) + C(suite) + C(implementation):C(suite)",
                data=df.dropna(subset=["throughput_mb_s"]),
            ).fit()
            anova_results = anova_lm(model, typ=2)
            print(anova_results)
        except Exception as e:
            print(f"⚠️  2-way ANOVA failed: {e}")


def create_visualizations(df, output_dir):
    """Create enhanced visualizations"""
    print("\n📊 Generowanie wykresów...")

    figures_dir = Path("figures")
    figures_dir.mkdir(exist_ok=True)

    plt.style.use("seaborn-v0_8")

    # 1. CPU Cycles per Byte comparison
    if (
        "cpu_cycles_per_byte" in df.columns
        and df["cpu_cycles_per_byte"].notna().sum() > 0
    ):
        plt.figure(figsize=(12, 6))

        # Box plot by suite
        plt.subplot(1, 2, 1)
        cycles_data = df.dropna(subset=["cpu_cycles_per_byte"])
        if len(cycles_data) > 0:
            sns.boxplot(data=cycles_data, x="suite", y="cpu_cycles_per_byte")
            plt.title("CPU Cycles per Byte by Algorithm Suite")
            plt.xlabel("Algorithm Suite")
            plt.ylabel("CPU Cycles per Byte")
            plt.xticks(rotation=45)

        # Implementation comparison
        plt.subplot(1, 2, 2)
        if len(cycles_data) > 0:
            sns.barplot(
                data=cycles_data,
                x="implementation",
                y="cpu_cycles_per_byte",
                hue="suite",
                ci=95,
            )
            plt.title("CPU Efficiency by Implementation")
            plt.xlabel("Implementation")
            plt.ylabel("CPU Cycles per Byte")
            plt.legend(title="Suite", bbox_to_anchor=(1.05, 1), loc="upper left")

        plt.tight_layout()
        plt.savefig(
            figures_dir / "cpu_cycles_per_byte.png", dpi=300, bbox_inches="tight"
        )
        plt.close()

    # 2. Energy Efficiency Dashboard
    if (
        "efficiency_mb_per_joule" in df.columns
        and df["efficiency_mb_per_joule"].notna().sum() > 0
    ):
        plt.figure(figsize=(15, 10))

        efficiency_data = df.dropna(subset=["efficiency_mb_per_joule"])

        # Energy efficiency by suite
        plt.subplot(2, 3, 1)
        sns.violinplot(data=efficiency_data, x="suite", y="efficiency_mb_per_joule")
        plt.title("Energy Efficiency by Suite")
        plt.xticks(rotation=45)

        # Power consumption
        if "package_watts" in df.columns:
            plt.subplot(2, 3, 2)
            power_data = df.dropna(subset=["package_watts"])
            if len(power_data) > 0:
                sns.barplot(data=power_data, x="suite", y="package_watts", ci=95)
                plt.title("Power Consumption")
                plt.xticks(rotation=45)

        # Efficiency vs Performance scatter
        plt.subplot(2, 3, 3)
        if "throughput_mb_s" in df.columns:
            throughput_data = df.dropna(
                subset=["efficiency_mb_per_joule", "throughput_mb_s"]
            )
            if len(throughput_data) > 0:
                scatter = sns.scatterplot(
                    data=throughput_data,
                    x="throughput_mb_s",
                    y="efficiency_mb_per_joule",
                    hue="suite",
                    size="package_watts",
                    sizes=(50, 200),
                )
                plt.title("Performance vs Energy Efficiency")
                plt.xlabel("Throughput (MB/s)")
                plt.ylabel("Efficiency (MB/s/W)")

        # Performance comparison
        plt.subplot(2, 3, 4)
        if "handshake_ms" in df.columns:
            handshake_data = df.dropna(subset=["handshake_ms"])
            if len(handshake_data) > 0:
                sns.boxplot(data=handshake_data, x="suite", y="handshake_ms")
                plt.title("Handshake Latency")
                plt.xticks(rotation=45)

        # Implementation heatmap
        plt.subplot(2, 3, 5)
        if len(efficiency_data) > 0:
            heatmap_data = (
                efficiency_data.groupby(["implementation", "suite"])[
                    "efficiency_mb_per_joule"
                ]
                .mean()
                .unstack()
            )
            if not heatmap_data.empty:
                sns.heatmap(heatmap_data, annot=True, fmt=".2f", cmap="RdYlGn")
                plt.title("Efficiency Heatmap")

        # CPU vs Energy correlation
        plt.subplot(2, 3, 6)
        if "cpu_cycles_per_byte" in df.columns:
            corr_data = df.dropna(
                subset=["cpu_cycles_per_byte", "efficiency_mb_per_joule"]
            )
            if len(corr_data) > 0:
                sns.scatterplot(
                    data=corr_data,
                    x="cpu_cycles_per_byte",
                    y="efficiency_mb_per_joule",
                    hue="suite",
                    alpha=0.7,
                )
                plt.title("CPU Efficiency vs Energy Efficiency")
                plt.xlabel("CPU Cycles per Byte")
                plt.ylabel("Energy Efficiency (MB/s/W)")

        plt.tight_layout()
        plt.savefig(
            figures_dir / "energy_efficiency_dashboard.png",
            dpi=300,
            bbox_inches="tight",
        )
        plt.close()

    # 3. Performance comparison matrix
    perf_metrics = [
        "handshake_ms",
        "throughput_mb_s",
        "cpu_cycles_per_byte",
        "package_watts",
    ]
    available_perf = [
        m for m in perf_metrics if m in df.columns and df[m].notna().sum() > 0
    ]

    if len(available_perf) >= 2:
        n_metrics = len(available_perf)
        fig, axes = plt.subplots(2, (n_metrics + 1) // 2, figsize=(15, 10))
        axes = axes.flatten() if n_metrics > 1 else [axes]

        for i, metric in enumerate(available_perf):
            if i < len(axes):
                metric_data = df.dropna(subset=[metric])
                if len(metric_data) > 0:
                    sns.boxplot(data=metric_data, x="suite", y=metric, ax=axes[i])
                    axes[i].set_title(f'{metric.replace("_", " ").title()}')
                    axes[i].tick_params(axis="x", rotation=45)

        # Hide empty subplots
        for i in range(len(available_perf), len(axes)):
            axes[i].set_visible(False)

        plt.tight_layout()
        plt.savefig(
            figures_dir / "performance_comparison.png", dpi=300, bbox_inches="tight"
        )
        plt.close()


def export_to_excel(df, output_dir):
    """Export enhanced results to Excel"""
    excel_path = output_dir / "analysis_results.xlsx"

    with pd.ExcelWriter(excel_path, engine="openpyxl") as writer:
        # Raw data
        df.to_excel(writer, sheet_name="Raw_Data", index=False)

        # Summary statistics
        numeric_cols = df.select_dtypes(include=[np.number]).columns
        summary = df[numeric_cols].describe()
        summary.to_excel(writer, sheet_name="Summary_Stats")

        # Performance by suite
        if "suite" in df.columns:
            suite_summary = (
                df.groupby("suite")[numeric_cols].agg(["mean", "std"]).round(3)
            )
            suite_summary.to_excel(writer, sheet_name="By_Suite")

        # Implementation comparison
        if "implementation" in df.columns:
            impl_summary = (
                df.groupby("implementation")[numeric_cols].agg(["mean", "std"]).round(3)
            )
            impl_summary.to_excel(writer, sheet_name="By_Implementation")

        # CPU Efficiency analysis
        efficiency_metrics = [
            "cpu_cycles_per_byte",
            "efficiency_mb_per_joule",
            "package_watts",
        ]
        available_eff = [m for m in efficiency_metrics if m in df.columns]
        if available_eff:
            efficiency_df = df[["suite", "implementation"] + available_eff].dropna()
            if len(efficiency_df) > 0:
                efficiency_df.to_excel(
                    writer, sheet_name="CPU_Energy_Efficiency", index=False
                )

    print(f"✓ Excel zapisany: {excel_path}")


def main():
    # Load data
    df, run_dir, netem_info = load_latest_results()

    # Prepare data
    pivot_df = prepare_data(df)

    # Show NetEm config
    print(
        f"\n🌐 NetEm włączony: delay={netem_info['delay']}ms, loss={netem_info['loss']}%"
    )

    # Statistical analysis
    statistical_analysis(pivot_df)

    # Create visualizations
    create_visualizations(pivot_df, run_dir)

    # Export to Excel
    export_to_excel(pivot_df, run_dir)

    print(f"\n✅ Analiza ukończona!")
    print(f"📁 Wykresy: figures")
    print(f"📁 Excel: {run_dir.name}/analysis_results.xlsx")

    # Key insights summary
    print(f"\n⚡ Podsumowanie wydajności:")

    # CPU cycles per byte summary
    if "cpu_cycles_per_byte" in pivot_df.columns:
        cycles_summary = (
            pivot_df.groupby("suite")["cpu_cycles_per_byte"]
            .agg(["mean", "std"])
            .round(2)
        )
        print("🔄 CPU Cycles per Byte:")
        for suite, data in cycles_summary.iterrows():
            print(f"   {suite}: {data['mean']:.2f} ± {data['std']:.2f}")

    # Energy efficiency
    if "efficiency_mb_per_joule" in pivot_df.columns:
        eff_summary = (
            pivot_df.groupby("suite")["efficiency_mb_per_joule"]
            .agg(["mean", "std"])
            .round(3)
        )
        print("💚 Energy Efficiency (MB/s/W):")
        for suite, data in eff_summary.iterrows():
            print(f"   {suite}: {data['mean']:.3f} ± {data['std']:.3f}")

    # Performance ranking
    key_metrics = ["handshake_ms", "throughput_mb_s", "cpu_cycles_per_byte"]
    available_metrics = [m for m in key_metrics if m in pivot_df.columns]

    if available_metrics:
        print(f"\n🏆 Ranking wydajności (według suite):")
        for metric in available_metrics:
            ranking = pivot_df.groupby("suite")[metric].mean().sort_values()
            print(f"\n📊 {metric}:")
            for i, (suite, value) in enumerate(ranking.items(), 1):
                print(f"   {i}. {suite}: {value:.2f}")


if __name__ == "__main__":
    main()
