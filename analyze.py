#!/usr/bin/env python3
"""
Enhanced analysis focusing on meaningful TLS performance metrics
Removed misleading crypto operation comparisons
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
    """Prepare and pivot data with focus on meaningful TLS metrics"""

    # Map metrics to more readable names - REMOVED misleading crypto metrics
    metric_mapping = {
        "mean_ms": "handshake_ms",
        "rps": "throughput_rps",
        "mean_time_s": "response_time_s",
        "throughput_mb_s": "throughput_mb_s",
        # REMOVED: "cpu_cycles_per_byte" - misleading comparison
        # REMOVED: "efficiency_mb_per_joule" - based on wrong measurements
        # REMOVED: "crypto_operation_ms" - apples vs oranges
        # REMOVED: "crypto_throughput_mb_s" - symmetric vs asymmetric
    }

    # Apply mapping
    df["metric_clean"] = df["metric"].map(metric_mapping).fillna(df["metric"])

    # Filter out misleading metrics
    meaningful_metrics = [
        "handshake_ms",
        "throughput_rps",
        "response_time_s",
        "throughput_mb_s",
        "stddev_ms",
        "samples",
        "failed_measurements",
        "failed_requests",
    ]

    df_filtered = df[df["metric_clean"].isin(meaningful_metrics)]

    if len(df_filtered) == 0:
        print("⚠️  No meaningful metrics found, using all data")
        df_filtered = df

    # Pivot to wide format
    try:
        pivot = df_filtered.pivot_table(
            index=["implementation", "suite", "test", "run"],
            columns="metric_clean",
            values="value",
            aggfunc="first",
        ).reset_index()
    except Exception as e:
        print(f"⚠️  Pivot failed: {e}")
        print("Available metrics:", df_filtered["metric_clean"].unique())
        # Fallback: group by without pivot
        pivot = (
            df_filtered.groupby(
                ["implementation", "suite", "test", "run", "metric_clean"]
            )["value"]
            .first()
            .reset_index()
        )
        return pivot

    # Calculate derived metrics only from meaningful data
    if "throughput_rps" in pivot.columns and pivot["throughput_rps"].notna().sum() > 0:
        # Estimate MB/s from RPS (assuming 1MB payload size)
        pivot["estimated_throughput_mb_s"] = pivot["throughput_rps"] * 1.0

    # Map suites to algorithms for better understanding
    suite_mapping = {
        "x25519_aesgcm": "Traditional (X25519+AES-GCM)",
        "chacha20": "Traditional (X25519+ChaCha20)",
        "kyber_hybrid": "Post-Quantum (X25519+ML-KEM768)",
    }
    pivot["algorithm"] = pivot["suite"].map(suite_mapping).fillna(pivot["suite"])

    # Add quantum resistance flag
    pivot["quantum_resistant"] = pivot["suite"].apply(
        lambda x: "Post-Quantum" if "kyber" in x else "Traditional"
    )

    return pivot


def statistical_analysis(df):
    """Enhanced statistical analysis focusing on meaningful TLS metrics"""
    print("\n📈 Statystyki opisowe (meaningful TLS metrics only):")

    # Focus on meaningful TLS performance metrics
    key_metrics = [
        "handshake_ms",  # ✅ Total connection establishment time
        "throughput_rps",  # ✅ Requests per second
        "throughput_mb_s",  # ✅ Data transfer rate
        "response_time_s",  # ✅ End-to-end response time
    ]

    available_metrics = [
        m for m in key_metrics if m in df.columns and df[m].notna().sum() > 0
    ]

    if available_metrics:
        desc_stats = df[available_metrics].describe()
        print(desc_stats.loc[["mean", "std", "min", "max"]].round(3))

        print(f"\n📊 Post-Quantum vs Traditional Performance Impact:")
        if "quantum_resistant" in df.columns:
            for metric in available_metrics:
                if df[metric].notna().sum() > 10:
                    try:
                        traditional = df[df["quantum_resistant"] == "Traditional"][
                            metric
                        ].dropna()
                        pq = df[df["quantum_resistant"] == "Post-Quantum"][
                            metric
                        ].dropna()

                        if len(traditional) > 0 and len(pq) > 0:
                            trad_mean = traditional.mean()
                            pq_mean = pq.mean()

                            if metric in ["handshake_ms", "response_time_s"]:
                                # For latency metrics, higher is worse
                                impact = ((pq_mean - trad_mean) / trad_mean) * 100
                                direction = "slower" if impact > 0 else "faster"
                            else:
                                # For throughput metrics, higher is better
                                impact = ((pq_mean - trad_mean) / trad_mean) * 100
                                direction = "better" if impact > 0 else "worse"

                            print(f"   {metric}: PQ is {abs(impact):.1f}% {direction}")
                    except Exception as e:
                        print(f"   ⚠️  Analysis failed for {metric}: {e}")
    else:
        print("⚠️  No meaningful metrics found for analysis")
        print("Available columns:", list(df.columns))
        return

    print(f"\n📈 Statistical Tests (ANOVA):")

    # Test each meaningful metric
    for metric in available_metrics:
        data_for_metric = df[df[metric].notna()]
        if len(data_for_metric) > 10:  # Need enough data points
            try:
                # 1-way ANOVA by algorithm suite
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
                    print(f"   {metric}: F={f_stat:.2f}, p={p_val:.3e} {significance}")
            except Exception as e:
                print(f"⚠️  ANOVA failed for {metric}: {e}")

    # Test for post-quantum impact
    if "quantum_resistant" in df.columns:
        print(f"\n📈 Post-Quantum Impact Tests (t-test):")
        for metric in available_metrics:
            data_for_metric = df[df[metric].notna()]
            if len(data_for_metric) > 10:
                try:
                    traditional = data_for_metric[
                        data_for_metric["quantum_resistant"] == "Traditional"
                    ][metric]
                    pq = data_for_metric[
                        data_for_metric["quantum_resistant"] == "Post-Quantum"
                    ][metric]

                    if len(traditional) > 5 and len(pq) > 5:
                        t_stat, p_val = stats.ttest_ind(traditional, pq)
                        significance = (
                            "***"
                            if p_val < 0.001
                            else "**" if p_val < 0.01 else "*" if p_val < 0.05 else ""
                        )
                        print(
                            f"   {metric}: t={t_stat:.2f}, p={p_val:.3e} {significance}"
                        )
                except Exception as e:
                    print(f"⚠️  t-test failed for {metric}: {e}")


def create_visualizations(df, output_dir):
    """Create focused visualizations for TLS performance"""
    print("\n📊 Generowanie wykresów...")

    figures_dir = Path("figures")
    figures_dir.mkdir(exist_ok=True)

    plt.style.use("default")
    sns.set_palette("husl")

    # 1. Main TLS Performance Comparison
    fig, axes = plt.subplots(2, 2, figsize=(16, 12))
    fig.suptitle(
        "TLS Performance Analysis: Post-Quantum vs Traditional",
        fontsize=16,
        fontweight="bold",
    )

    # Handshake latency comparison
    if "handshake_ms" in df.columns and df["handshake_ms"].notna().sum() > 0:
        handshake_data = df.dropna(subset=["handshake_ms"])
        sns.boxplot(data=handshake_data, x="algorithm", y="handshake_ms", ax=axes[0, 0])
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
        sns.boxplot(
            data=throughput_data, x="algorithm", y=throughput_col, ax=axes[0, 1]
        )
        axes[0, 1].set_title("Throughput Performance")
        axes[0, 1].set_xlabel("Algorithm Suite")
        ylabel = "Throughput (MB/s)" if "mb_s" in throughput_col else "Requests/sec"
        axes[0, 1].set_ylabel(ylabel)
        axes[0, 1].tick_params(axis="x", rotation=45)

    # Implementation comparison for handshake
    if "handshake_ms" in df.columns:
        handshake_data = df.dropna(subset=["handshake_ms"])
        if len(handshake_data) > 0:
            sns.barplot(
                data=handshake_data,
                x="implementation",
                y="handshake_ms",
                hue="quantum_resistant",
                ax=axes[1, 0],
            )
            axes[1, 0].set_title("Handshake Performance by Implementation")
            axes[1, 0].set_xlabel("SSL/TLS Implementation")
            axes[1, 0].set_ylabel("Handshake Time (ms)")
            axes[1, 0].legend(title="Crypto Type")

    # Response time distribution
    if "response_time_s" in df.columns and df["response_time_s"].notna().sum() > 0:
        response_data = df.dropna(subset=["response_time_s"])
        sns.violinplot(
            data=response_data,
            x="quantum_resistant",
            y="response_time_s",
            ax=axes[1, 1],
        )
        axes[1, 1].set_title("Response Time Distribution")
        axes[1, 1].set_xlabel("Cryptography Type")
        axes[1, 1].set_ylabel("Response Time (s)")

    plt.tight_layout()
    plt.savefig(
        figures_dir / "tls_performance_comparison.png", dpi=300, bbox_inches="tight"
    )
    plt.close()

    # 2. Post-Quantum Impact Analysis
    if "quantum_resistant" in df.columns:
        metrics_to_plot = []
        for metric in ["handshake_ms", "throughput_rps", "response_time_s"]:
            if metric in df.columns and df[metric].notna().sum() > 0:
                metrics_to_plot.append(metric)

        if metrics_to_plot:
            n_metrics = len(metrics_to_plot)
            fig, axes = plt.subplots(1, n_metrics, figsize=(6 * n_metrics, 6))
            if n_metrics == 1:
                axes = [axes]

            fig.suptitle(
                "Post-Quantum Cryptography Performance Impact",
                fontsize=16,
                fontweight="bold",
            )

            for i, metric in enumerate(metrics_to_plot):
                metric_data = df.dropna(subset=[metric])
                if len(metric_data) > 0:
                    sns.boxplot(
                        data=metric_data, x="quantum_resistant", y=metric, ax=axes[i]
                    )

                    # Calculate and show performance impact
                    traditional = metric_data[
                        metric_data["quantum_resistant"] == "Traditional"
                    ][metric]
                    pq = metric_data[
                        metric_data["quantum_resistant"] == "Post-Quantum"
                    ][metric]

                    if len(traditional) > 0 and len(pq) > 0:
                        trad_mean = traditional.mean()
                        pq_mean = pq.mean()
                        impact = ((pq_mean - trad_mean) / trad_mean) * 100

                        title = metric.replace("_", " ").title()
                        if metric in ["handshake_ms", "response_time_s"]:
                            direction = "slower" if impact > 0 else "faster"
                        else:
                            direction = "worse" if impact < 0 else "better"

                        axes[i].set_title(f"{title}\n(PQ: {impact:+.1f}% {direction})")
                    else:
                        axes[i].set_title(metric.replace("_", " ").title())

            plt.tight_layout()
            plt.savefig(
                figures_dir / "post_quantum_impact.png", dpi=300, bbox_inches="tight"
            )
            plt.close()

    # 3. Implementation Detailed Comparison
    implementations = (
        df["implementation"].unique() if "implementation" in df.columns else []
    )
    if len(implementations) > 1:
        fig, axes = plt.subplots(1, 2, figsize=(14, 6))
        fig.suptitle(
            "Implementation Performance Comparison", fontsize=16, fontweight="bold"
        )

        # Handshake performance by implementation and suite
        if "handshake_ms" in df.columns:
            handshake_data = df.dropna(subset=["handshake_ms"])
            if len(handshake_data) > 0:
                sns.barplot(
                    data=handshake_data,
                    x="implementation",
                    y="handshake_ms",
                    hue="suite",
                    ax=axes[0],
                )
                axes[0].set_title("Handshake Latency by Implementation")
                axes[0].set_ylabel("Handshake Time (ms)")
                axes[0].legend(
                    title="Algorithm Suite", bbox_to_anchor=(1.05, 1), loc="upper left"
                )

        # Throughput by implementation
        if throughput_col:
            throughput_data = df.dropna(subset=[throughput_col])
            if len(throughput_data) > 0:
                sns.barplot(
                    data=throughput_data,
                    x="implementation",
                    y=throughput_col,
                    hue="suite",
                    ax=axes[1],
                )
                axes[1].set_title("Throughput by Implementation")
                ylabel = (
                    "Throughput (MB/s)" if "mb_s" in throughput_col else "Requests/sec"
                )
                axes[1].set_ylabel(ylabel)
                axes[1].legend(
                    title="Algorithm Suite", bbox_to_anchor=(1.05, 1), loc="upper left"
                )

        plt.tight_layout()
        plt.savefig(
            figures_dir / "implementation_comparison.png", dpi=300, bbox_inches="tight"
        )
        plt.close()

    print(f"✓ Wykresy zapisane w: {figures_dir}")


def export_to_excel(df, output_dir):
    """Export enhanced results to Excel"""
    excel_path = output_dir / "tls_analysis_results.xlsx"

    try:
        with pd.ExcelWriter(excel_path, engine="openpyxl") as writer:
            # Raw data
            df.to_excel(writer, sheet_name="Raw_Data", index=False)

            # Summary statistics for meaningful metrics
            meaningful_metrics = [
                "handshake_ms",
                "throughput_rps",
                "response_time_s",
                "throughput_mb_s",
            ]
            available_meaningful = [
                m
                for m in meaningful_metrics
                if m in df.columns and df[m].notna().sum() > 0
            ]

            if available_meaningful:
                summary = df[available_meaningful].describe()
                summary.to_excel(writer, sheet_name="Summary_Stats")

            # Performance by algorithm suite
            if "suite" in df.columns and available_meaningful:
                suite_summary = (
                    df.groupby("suite")[available_meaningful]
                    .agg(["mean", "std"])
                    .round(3)
                )
                suite_summary.to_excel(writer, sheet_name="By_Algorithm")

            # Implementation comparison
            if "implementation" in df.columns and available_meaningful:
                impl_summary = (
                    df.groupby("implementation")[available_meaningful]
                    .agg(["mean", "std"])
                    .round(3)
                )
                impl_summary.to_excel(writer, sheet_name="By_Implementation")

            # Post-quantum impact analysis
            if "quantum_resistant" in df.columns and available_meaningful:
                pq_summary = (
                    df.groupby("quantum_resistant")[available_meaningful]
                    .agg(["mean", "std", "count"])
                    .round(3)
                )
                pq_summary.to_excel(writer, sheet_name="PostQuantum_Impact")

        print(f"✓ Excel zapisany: {excel_path}")
    except Exception as e:
        print(f"⚠️  Excel export failed: {e}")


def print_summary_insights(df):
    """Print key insights focusing on meaningful TLS performance"""
    print(f"\n⚡ Podsumowanie wydajności TLS:")

    # Algorithm performance ranking for meaningful metrics
    performance_metrics = {
        "handshake_ms": ("🔄 Handshake Latency (ms)", False),  # Lower is better
        "throughput_rps": ("📈 Throughput (RPS)", True),  # Higher is better
        "response_time_s": ("⏱️  Response Time (s)", False),  # Lower is better
        "throughput_mb_s": ("🚀 Transfer Rate (MB/s)", True),  # Higher is better
    }

    for metric, (label, higher_better) in performance_metrics.items():
        if metric in df.columns and df[metric].notna().sum() > 0:
            ranking = df.groupby("algorithm")[metric].mean()
            if higher_better:
                ranking = ranking.sort_values(ascending=False)
            else:
                ranking = ranking.sort_values(ascending=True)

            print(f"\n{label}:")
            for i, (suite, value) in enumerate(ranking.items(), 1):
                medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else "  "
                print(f"   {medal} {i}. {suite}: {value:.3f}")

    # Post-quantum impact summary
    if "quantum_resistant" in df.columns:
        print(f"\n📊 Post-Quantum Cryptography Impact:")
        for metric, (label, higher_better) in performance_metrics.items():
            if metric in df.columns and df[metric].notna().sum() > 10:
                try:
                    traditional = df[df["quantum_resistant"] == "Traditional"][
                        metric
                    ].dropna()
                    pq = df[df["quantum_resistant"] == "Post-Quantum"][metric].dropna()

                    if len(traditional) > 0 and len(pq) > 0:
                        trad_mean = traditional.mean()
                        pq_mean = pq.mean()
                        impact = ((pq_mean - trad_mean) / trad_mean) * 100

                        if metric in ["handshake_ms", "response_time_s"]:
                            # For latency metrics, positive impact = worse (slower)
                            status = (
                                "⚠️" if impact > 5 else "✅" if impact > -5 else "🚀"
                            )
                            direction = "slower" if impact > 0 else "faster"
                        else:
                            # For throughput metrics, positive impact = better
                            status = (
                                "🚀" if impact > 5 else "✅" if impact > -5 else "⚠️"
                            )
                            direction = "better" if impact > 0 else "worse"

                        print(f"   {status} {label}: {abs(impact):.1f}% {direction}")
                except Exception:
                    pass

    # Implementation comparison
    if "implementation" in df.columns:
        print(f"\n🏗️  Best Implementation (by handshake speed):")
        if "handshake_ms" in df.columns:
            impl_perf = (
                df.groupby("implementation")["handshake_ms"].mean().sort_values()
            )
            for i, (impl, time) in enumerate(impl_perf.items(), 1):
                medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉"
                print(f"   {medal} {impl}: {time:.2f}ms average")

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

    print(f"\n💡 Key Takeaways:")
    print(f"   ✓ Analysis focuses on end-to-end TLS performance")
    print(f"   ✓ Meaningful metrics: handshake, throughput, response time")
    print(f"   ✓ Removed misleading crypto operation comparisons")
    print(f"   ✓ Shows real-world post-quantum adoption cost")


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

    # Prepare data with focus on meaningful TLS metrics
    try:
        pivot_df = prepare_data(df)
        print(f"📊 Prepared {len(pivot_df)} data points for analysis")
        print(f"📊 Focus: Meaningful TLS performance metrics only")
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
    print(f"\n📋 Note: Analysis now focuses on meaningful TLS metrics")
    print(f"   Removed misleading crypto operation comparisons")


if __name__ == "__main__":
    main()
