#!/usr/bin/env python3
"""
Enhanced analysis with CPU cycles per byte - Fixed CSV parsing
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
import json
import sys
import re
from scipy import stats
from statsmodels.stats.anova import anova_lm
from statsmodels.formula.api import ols
import warnings

warnings.filterwarnings("ignore")


def load_latest_results():
    """Load results from latest/ symlink with robust CSV parsing"""
    results_dir = Path("results")
    latest_link = results_dir / "latest"

    if not latest_link.exists():
        print("❌ Brak results/latest - uruchom najpierw benchmarki")
        sys.exit(1)

    run_dir = latest_link.resolve()
    print(f"📊 Analiza najnowszego: {run_dir.name}")

    # Load main CSV with robust parsing
    csv_path = run_dir / "bench.csv"
    if not csv_path.exists():
        print(f"❌ Brak {csv_path}")
        sys.exit(1)

    # Read CSV with custom handling for raw_measurements arrays
    df = read_csv_robust(csv_path)

    # Load config for NetEm info
    config_path = run_dir / "config.txt"
    netem_info = {"delay": 0, "loss": 0.0}
    if config_path.exists():
        with open(config_path) as f:
            content = f.read()
            if "delay=" in content:
                delay_match = re.search(r"delay=(\d+)ms", content)
                loss_match = re.search(r"loss=([\d.]+)", content)
                if delay_match:
                    netem_info["delay"] = int(delay_match.group(1))
                if loss_match:
                    netem_info["loss"] = float(loss_match.group(1))

    return df, run_dir, netem_info


def read_csv_robust(csv_path):
    """Robust CSV reader that handles arrays in raw_measurements"""
    try:
        # First try standard pandas read
        return pd.read_csv(csv_path)
    except pd.errors.ParserError:
        print("⚠️  Standard CSV parsing failed, using robust method...")

        rows = []
        expected_columns = [
            "implementation",
            "suite",
            "test",
            "run",
            "metric",
            "value",
            "unit",
        ]

        with open(csv_path, "r") as f:
            header_line = f.readline().strip()

            # Verify header
            if header_line.startswith("implementation,suite,test"):
                expected_columns = header_line.split(",")

            for line_num, line in enumerate(f, 2):
                line = line.strip()
                if not line:
                    continue

                # Handle lines with array data in raw_measurements
                if "[" in line and "]" in line:
                    # Extract the array part and treat it as a single field
                    parts = []
                    in_array = False
                    current_field = ""

                    i = 0
                    while i < len(line):
                        char = line[i]

                        if char == "[":
                            in_array = True
                            current_field += char
                        elif char == "]":
                            in_array = False
                            current_field += char
                        elif char == "," and not in_array:
                            parts.append(current_field.strip())
                            current_field = ""
                        else:
                            current_field += char
                        i += 1

                    # Add the last field
                    if current_field:
                        parts.append(current_field.strip())
                else:
                    # Normal CSV line
                    parts = [p.strip() for p in line.split(",")]

                # Ensure we have the right number of fields
                while len(parts) < len(expected_columns):
                    parts.append("")

                if len(parts) >= len(expected_columns):
                    row_dict = {}
                    for i, col in enumerate(expected_columns):
                        if i < len(parts):
                            row_dict[col] = parts[i]
                        else:
                            row_dict[col] = ""
                    rows.append(row_dict)
                else:
                    print(f"⚠️  Skipping malformed line {line_num}: {line[:50]}...")

        df = pd.DataFrame(rows)

        # Convert numeric columns
        numeric_columns = ["run", "value"]
        for col in numeric_columns:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        print(f"✓ Loaded {len(df)} rows with robust parsing")
        return df


def prepare_data(df):
    """Prepare and pivot data with enhanced metrics"""

    # Map metrics to more readable names
    metric_mapping = {
        "mean_ms": "handshake_ms",
        "rps": "throughput_rps",
        "mean_time_s": "response_time_s",
        "package_watts": "package_watts",
        "cpu_cycles_per_byte": "cpu_cycles_per_byte",
        "efficiency_mb_per_joule": "efficiency_mb_per_joule",
        "crypto_operation_ms": "crypto_operation_ms",
        "total_cpu_cycles": "total_cpu_cycles",
        "throughput_mb_s": "throughput_mb_s",
        "crypto_throughput_mb_s": "crypto_throughput_mb_s",
    }

    # Apply mapping
    df["metric_clean"] = df["metric"].map(metric_mapping).fillna(df["metric"])

    # Pivot to wide format
    try:
        pivot = df.pivot_table(
            index=["implementation", "suite", "test", "run"],
            columns="metric_clean",
            values="value",
            aggfunc="first",
        ).reset_index()
    except Exception as e:
        print(f"⚠️  Pivot failed: {e}")
        print("Available metrics:", df["metric"].unique())
        # Fallback: group by without pivot
        pivot = (
            df.groupby(["implementation", "suite", "test", "run", "metric"])["value"]
            .first()
            .reset_index()
        )
        return pivot

    # Calculate derived metrics
    if "throughput_rps" in pivot.columns and pivot["throughput_rps"].notna().sum() > 0:
        pivot["throughput_mb_s"] = (
            pivot["throughput_rps"] * 1.0
        )  # Assume ~1MB per request

    # Map suites to algorithms for better understanding
    suite_mapping = {
        "x25519_aesgcm": "X25519 + AES-GCM",
        "chacha20": "X25519 + ChaCha20",
        "kyber_hybrid": "X25519+ML-KEM768",
    }
    pivot["algorithm"] = pivot["suite"].map(suite_mapping).fillna(pivot["suite"])

    return pivot


def statistical_analysis(df):
    """Enhanced statistical analysis with new metrics"""
    print("\n📈 Statystyki opisowe:")

    # Focus on key metrics
    key_metrics = [
        "handshake_ms",
        "throughput_mb_s",
        "throughput_rps",
        "response_time_s",
        "package_watts",
        "cpu_cycles_per_byte",
        "efficiency_mb_per_joule",
        "crypto_operation_ms",
        "crypto_throughput_mb_s",
    ]

    available_metrics = [
        m for m in key_metrics if m in df.columns and df[m].notna().sum() > 0
    ]

    if available_metrics:
        desc_stats = df[available_metrics].describe()
        print(desc_stats.loc[["mean", "std", "min", "max"]].round(3))
    else:
        print("⚠️  No numeric metrics found for analysis")
        print("Available columns:", list(df.columns))
        return

    print(f"\n📈 Testy ANOVA:")

    # Test each metric
    for metric in available_metrics:
        data_for_metric = df[df[metric].notna()]
        if len(data_for_metric) > 10:  # Need enough data points
            try:
                # 1-way ANOVA by suite
                groups = [
                    group[metric].dropna()
                    for name, group in data_for_metric.groupby("suite")
                ]
                groups = [g for g in groups if len(g) > 1]

                if len(groups) >= 2:
                    f_stat, p_val = stats.f_oneway(*groups)
                    significance = (
                        "***"
                        if p_val < 0.001
                        else "**" if p_val < 0.01 else "*" if p_val < 0.05 else ""
                    )
                    print(
                        f"[1-way] {metric}: F={f_stat:.2f}, p={p_val:.3e} {significance}"
                    )
            except Exception as e:
                print(f"⚠️  ANOVA failed for {metric}: {e}")

    # 2-way ANOVA for key performance metrics
    for metric in ["throughput_mb_s", "handshake_ms"]:
        if metric in df.columns and df[metric].notna().sum() > 10:
            try:
                clean_data = df.dropna(subset=[metric])
                if len(clean_data) > 20:  # Need sufficient data for 2-way
                    print(f"\n[2-way ANOVA] {metric}")
                    model = ols(
                        f"{metric} ~ C(implementation) + C(suite) + C(implementation):C(suite)",
                        data=clean_data,
                    ).fit()
                    anova_results = anova_lm(model, typ=2)
                    print(anova_results)
            except Exception as e:
                print(f"⚠️  2-way ANOVA failed for {metric}: {e}")


def create_visualizations(df, output_dir):
    """Create enhanced visualizations"""
    print("\n📊 Generowanie wykresów...")

    figures_dir = Path("figures")
    figures_dir.mkdir(exist_ok=True)

    plt.style.use("default")  # Use default style as seaborn-v0_8 might not be available
    sns.set_palette("husl")

    # 1. Performance Overview
    fig, axes = plt.subplots(2, 2, figsize=(15, 12))
    fig.suptitle("TLS Performance Analysis Overview", fontsize=16, fontweight="bold")

    # Handshake latency
    if "handshake_ms" in df.columns and df["handshake_ms"].notna().sum() > 0:
        handshake_data = df.dropna(subset=["handshake_ms"])
        sns.boxplot(data=handshake_data, x="suite", y="handshake_ms", ax=axes[0, 0])
        axes[0, 0].set_title("TLS Handshake Latency")
        axes[0, 0].set_xlabel("Algorithm Suite")
        axes[0, 0].set_ylabel("Latency (ms)")
        axes[0, 0].tick_params(axis="x", rotation=45)

    # Throughput comparison
    throughput_col = None
    for col in ["throughput_mb_s", "throughput_rps"]:
        if col in df.columns and df[col].notna().sum() > 0:
            throughput_col = col
            break

    if throughput_col:
        throughput_data = df.dropna(subset=[throughput_col])
        sns.boxplot(data=throughput_data, x="suite", y=throughput_col, ax=axes[0, 1])
        axes[0, 1].set_title("Throughput Performance")
        axes[0, 1].set_xlabel("Algorithm Suite")
        ylabel = "Throughput (MB/s)" if "mb_s" in throughput_col else "Requests/sec"
        axes[0, 1].set_ylabel(ylabel)
        axes[0, 1].tick_params(axis="x", rotation=45)

    # Implementation comparison
    if "handshake_ms" in df.columns:
        handshake_data = df.dropna(subset=["handshake_ms"])
        if len(handshake_data) > 0:
            sns.barplot(
                data=handshake_data,
                x="implementation",
                y="handshake_ms",
                hue="suite",
                ax=axes[1, 0],
            )
            axes[1, 0].set_title("Handshake by Implementation")
            axes[1, 0].set_xlabel("SSL/TLS Implementation")
            axes[1, 0].set_ylabel("Handshake Time (ms)")
            axes[1, 0].legend(
                title="Algorithm", bbox_to_anchor=(1.05, 1), loc="upper left"
            )

    # Response time distribution
    if "response_time_s" in df.columns and df["response_time_s"].notna().sum() > 0:
        response_data = df.dropna(subset=["response_time_s"])
        sns.violinplot(
            data=response_data, x="suite", y="response_time_s", ax=axes[1, 1]
        )
        axes[1, 1].set_title("Response Time Distribution")
        axes[1, 1].set_xlabel("Algorithm Suite")
        axes[1, 1].set_ylabel("Response Time (s)")
        axes[1, 1].tick_params(axis="x", rotation=45)

    plt.tight_layout()
    plt.savefig(figures_dir / "performance_overview.png", dpi=300, bbox_inches="tight")
    plt.close()

    # 2. CPU and Energy Efficiency Analysis
    energy_metrics = ["cpu_cycles_per_byte", "efficiency_mb_per_joule", "package_watts"]
    available_energy = [
        m for m in energy_metrics if m in df.columns and df[m].notna().sum() > 0
    ]

    if available_energy:
        n_metrics = len(available_energy)
        fig, axes = plt.subplots(1, n_metrics, figsize=(5 * n_metrics, 6))
        if n_metrics == 1:
            axes = [axes]

        fig.suptitle("Energy Efficiency Analysis", fontsize=16, fontweight="bold")

        for i, metric in enumerate(available_energy):
            metric_data = df.dropna(subset=[metric])
            if len(metric_data) > 0:
                sns.boxplot(data=metric_data, x="suite", y=metric, ax=axes[i])
                title = metric.replace("_", " ").title()
                axes[i].set_title(title)
                axes[i].tick_params(axis="x", rotation=45)

        plt.tight_layout()
        plt.savefig(figures_dir / "energy_efficiency.png", dpi=300, bbox_inches="tight")
        plt.close()

    # 3. Crypto Operations Performance
    crypto_metrics = ["crypto_operation_ms", "crypto_throughput_mb_s"]
    available_crypto = [
        m for m in crypto_metrics if m in df.columns and df[m].notna().sum() > 0
    ]

    if available_crypto:
        fig, axes = plt.subplots(1, len(available_crypto), figsize=(12, 6))
        if len(available_crypto) == 1:
            axes = [axes]

        fig.suptitle(
            "Cryptographic Operations Performance", fontsize=16, fontweight="bold"
        )

        for i, metric in enumerate(available_crypto):
            crypto_data = df.dropna(subset=[metric])
            if len(crypto_data) > 0:
                sns.barplot(
                    data=crypto_data,
                    x="suite",
                    y=metric,
                    hue="implementation",
                    ax=axes[i],
                )
                title = metric.replace("_", " ").title()
                axes[i].set_title(title)
                axes[i].tick_params(axis="x", rotation=45)
                axes[i].legend(title="Implementation")

        plt.tight_layout()
        plt.savefig(
            figures_dir / "crypto_performance.png", dpi=300, bbox_inches="tight"
        )
        plt.close()

    print(f"✓ Wykresy zapisane w: {figures_dir}")


def export_to_excel(df, output_dir):
    """Export enhanced results to Excel"""
    excel_path = output_dir / "analysis_results.xlsx"

    try:
        with pd.ExcelWriter(excel_path, engine="openpyxl") as writer:
            # Raw data
            df.to_excel(writer, sheet_name="Raw_Data", index=False)

            # Summary statistics
            numeric_cols = df.select_dtypes(include=[np.number]).columns
            if len(numeric_cols) > 0:
                summary = df[numeric_cols].describe()
                summary.to_excel(writer, sheet_name="Summary_Stats")

            # Performance by suite
            if "suite" in df.columns and len(numeric_cols) > 0:
                suite_summary = (
                    df.groupby("suite")[numeric_cols].agg(["mean", "std"]).round(3)
                )
                suite_summary.to_excel(writer, sheet_name="By_Suite")

            # Implementation comparison
            if "implementation" in df.columns and len(numeric_cols) > 0:
                impl_summary = (
                    df.groupby("implementation")[numeric_cols]
                    .agg(["mean", "std"])
                    .round(3)
                )
                impl_summary.to_excel(writer, sheet_name="By_Implementation")

        print(f"✓ Excel zapisany: {excel_path}")
    except Exception as e:
        print(f"⚠️  Excel export failed: {e}")


def print_summary_insights(df):
    """Print key insights from the analysis"""
    print(f"\n⚡ Podsumowanie wydajności:")

    # Algorithm performance ranking
    performance_metrics = {
        "handshake_ms": ("🔄 Handshake Latency (ms)", False),  # Lower is better
        "throughput_mb_s": ("📈 Throughput (MB/s)", True),  # Higher is better
        "cpu_cycles_per_byte": ("💻 CPU Efficiency (cycles/byte)", False),
        "efficiency_mb_per_joule": ("💚 Energy Efficiency (MB/s/W)", True),
    }

    for metric, (label, higher_better) in performance_metrics.items():
        if metric in df.columns and df[metric].notna().sum() > 0:
            ranking = df.groupby("suite")[metric].mean()
            if higher_better:
                ranking = ranking.sort_values(ascending=False)
            else:
                ranking = ranking.sort_values(ascending=True)

            print(f"\n{label}:")
            for i, (suite, value) in enumerate(ranking.items(), 1):
                medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else "  "
                print(f"   {medal} {i}. {suite}: {value:.3f}")

    # Implementation comparison
    if "implementation" in df.columns:
        print(f"\n🏗️  Implementacje (średnia wydajność):")
        if "handshake_ms" in df.columns:
            impl_perf = (
                df.groupby("implementation")["handshake_ms"].mean().sort_values()
            )
            for impl, time in impl_perf.items():
                print(f"   • {impl}: {time:.2f}ms")

    # Data quality summary
    print(f"\n📊 Jakość danych:")
    print(f"   • Całkowita liczba pomiarów: {len(df)}")
    print(
        f"   • Implementacje: {df['implementation'].nunique() if 'implementation' in df.columns else 'N/A'}"
    )
    print(
        f"   • Algorytmy: {df['suite'].nunique() if 'suite' in df.columns else 'N/A'}"
    )
    print(
        f"   • Typy testów: {df['test'].nunique() if 'test' in df.columns else 'N/A'}"
    )


def main():
    # Load data
    try:
        df, run_dir, netem_info = load_latest_results()
    except Exception as e:
        print(f"❌ Error loading data: {e}")
        sys.exit(1)

    print(f"📋 Loaded {len(df)} measurements")

    # Show available metrics
    if "metric" in df.columns:
        print(f"📏 Available metrics: {sorted(df['metric'].unique())}")

    # Prepare data
    try:
        pivot_df = prepare_data(df)
        print(f"📊 Prepared {len(pivot_df)} data points for analysis")
    except Exception as e:
        print(f"⚠️  Data preparation failed: {e}")
        # Use original data as fallback
        pivot_df = df

    # Show NetEm config
    print(
        f"\n🌐 NetEm configuration: delay={netem_info['delay']}ms, loss={netem_info['loss']}%"
    )

    # Statistical analysis
    try:
        statistical_analysis(pivot_df)
    except Exception as e:
        print(f"⚠️  Statistical analysis failed: {e}")

    # Create visualizations
    try:
        create_visualizations(pivot_df, run_dir)
    except Exception as e:
        print(f"⚠️  Visualization creation failed: {e}")

    # Export to Excel
    try:
        export_to_excel(pivot_df, run_dir)
    except Exception as e:
        print(f"⚠️  Excel export failed: {e}")

    # Print insights
    try:
        print_summary_insights(pivot_df)
    except Exception as e:
        print(f"⚠️  Summary insights failed: {e}")

    print(f"\n✅ Analiza ukończona!")
    print(f"📁 Wykresy: figures/")
    print(f"📁 Wyniki: {run_dir.name}/")


if __name__ == "__main__":
    main()
